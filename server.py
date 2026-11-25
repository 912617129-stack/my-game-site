"""Skyline Kart private room relay (aiohttp). Host browser runs the simulation."""
import asyncio, json, os, secrets, time, hashlib, sqlite3, math, random
from pathlib import Path
from aiohttp import web, WSMsgType
ROOT=Path(__file__).resolve().parent
rooms={}

queues={'ranked':[], 'casual':[]}
ONLINE_RULES=('normal','noitems','elimination','turbo','grandprix')
GP_CUPS=((0,1,2,3),(1,2,3,4),(4,0,2,3),(5,0,4,3),(6,1,5,3),(7,8,5,6),(9,5,7,8),(10,13,14,17),(11,12,15,16),(18,19,20,21))
GP_POINTS=(15,12,10,8,6,4)
DBURL=os.environ.get('DATABASE_URL')
def db():
    if DBURL:
        import psycopg
        return psycopg.connect(DBURL)
    return sqlite3.connect(ROOT/'ranking.sqlite3')
def query(conn, sql, args=()):
    return conn.execute(sql.replace('?', '%s') if DBURL else sql,args)
def init_db():
    with db() as c:
        query(c,'CREATE TABLE IF NOT EXISTS players (id TEXT PRIMARY KEY, name TEXT NOT NULL, rating INTEGER NOT NULL DEFAULT 1000, wins INTEGER NOT NULL DEFAULT 0, games INTEGER NOT NULL DEFAULT 0)')
        query(c,'CREATE TABLE IF NOT EXISTS matches (id TEXT PRIMARY KEY)')
        query(c,'CREATE TABLE IF NOT EXISTS trial_records (account TEXT NOT NULL, course INTEGER NOT NULL, cc INTEGER NOT NULL, name TEXT NOT NULL, ms INTEGER NOT NULL, PRIMARY KEY(account,course,cc))')
def profile(token,name):
    if not isinstance(token,str) or len(token)!=64 or any(x not in '0123456789abcdef' for x in token): token=secrets.token_hex(32)
    pid=hashlib.sha256(token.encode()).hexdigest()
    with db() as c:
        query(c,'INSERT INTO players(id,name) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',(pid,clean_name(name)))
        row=query(c,'SELECT rating,wins,games FROM players WHERE id=?',(pid,)).fetchone()
    return token,pid,row[0]
async def presence(request):
    # Count connected human sessions only; CPU racers do not count.
    # WebSocket heartbeat/cleanup removes disconnected participants.
    counts={k:{'waiting':0,'playing':0} for k in queues}
    for kind, q in queues.items():
        counts[kind]['waiting']=sum(1 for player in q if not player['ws'].closed and not player.get('room'))
    for room in rooms.values():
        kind=room.get('kind')
        if kind in counts and room.get('phase')=='race':
            counts[kind]['playing']+=sum(1 for player in room['members'].values() if not player['ws'].closed)
    response=web.json_response({'casual':counts['casual'],'ranked':counts['ranked'],
                                'total':sum(group['waiting']+group['playing'] for group in counts.values())})
    response.headers['Cache-Control']='no-store, max-age=0'
    return response

async def ranking(request):
    with db() as c:
        rows=query(c,'SELECT name,rating,wins,games FROM players WHERE games>0 ORDER BY rating DESC,wins DESC,id LIMIT 100').fetchall()
    return web.json_response({'rows':[dict(name=r[0],rating=r[1],wins=r[2],games=r[3]) for r in rows], 'persistent':bool(DBURL)})
def settle(r, rows):
    members=r['rank_members']; ids=list(members)
    # Only server-issued participants count; CPU results never affect rating.
    order=[x['id'] for x in rows if isinstance(x,dict) and x.get('id') in ids]
    if len(order)!=len(ids) or len(set(order))!=len(ids): return None
    # Host simulation is not authoritative: reject malformed/implausibly fast finishes.
    if time.monotonic()-r['started']<25: return None
    for x in rows:
        if not isinstance(x,dict): return None
        t=x.get('time')
        if t is not None and (not isinstance(t,(int,float)) or not math.isfinite(t) or t<20 or t>1000): return None
    order=[i for i in order if i not in r['quit']]+[i for i in order if i in r['quit']]
    if order[0] in r['quit']: return None
    with db() as c:
        if not query(c,'INSERT INTO matches(id) VALUES (?) ON CONFLICT(id) DO NOTHING',(r['match_id'],)).rowcount: return None
        ratings={i:query(c,'SELECT rating FROM players WHERE id=?',(members[i]['account'],)).fetchone()[0] for i in ids}
        changes={}
        for i in ids:
            delta=round(32*sum((1 if order.index(i)<order.index(j) else 0)-1/(1+10**((ratings[j]-ratings[i])/400)) for j in ids if j!=i)/(len(ids)-1))
            if i in r['quit']: delta=min(delta,-20)
            new=max(0,ratings[i]+delta); changes[i]={'rating':new,'delta':new-ratings[i]}
            query(c,'UPDATE players SET rating=?,wins=wins+?,games=games+1 WHERE id=?',(new,int(i==order[0]),members[i]['account']))
    return changes
async def matchmaking(app):
    while True:
        await asyncio.sleep(1)
        for kind,q in queues.items():
            q[:]=[p for p in q if not p['ws'].closed]
            if not q: continue
            first=q[0]; elapsed=time.monotonic()-first['queued']; pool=[p for p in q if p.get('rule','normal')==first.get('rule','normal') and (kind=='casual' or abs(p['rating']-first['rating'])<=min(10000,150+elapsed*12))][:6]
            if len(pool)<6 and (elapsed<30 or len(pool)<(2 if kind=='ranked' else 1)):
                for p in q: await send(p['ws'],{'type':'queue','count':len(pool),'seconds':max(0,30-int(elapsed))})
                continue
            code=str(secrets.randbelow(900000)+100000)
            while code in rooms: code=str(secrets.randbelow(900000)+100000)
            r={'code':code,'host':'p1','members':{},'phase':'race','settings':{'course':random.randrange(22),'cc':1,'level':1,'cpu':6-len(pool),'rule':first.get('rule','normal') if kind=='casual' else 'normal'},'kind':kind,'started':time.monotonic(),'match_id':secrets.token_hex(16),'quit':set()}
            rooms[code]=r
            for i,p in enumerate(pool):
                q.remove(p); pid='p'+str(i+1); p['id']=pid;p['ready']=True;p['room']=r;r['members'][pid]=p
            r['rank_members']=dict(r['members'])
            for p in pool: await send(p['ws'],{'type':'joined','id':p['id'],'code':code,'kind':kind})
            payload=lobby(r);payload['type']='start';payload['kind']=kind;await broadcast(r,payload)
async def startup(app):
    init_db();app['match_task']=asyncio.create_task(matchmaking(app))
async def cleanup(app):
    app['match_task'].cancel();await asyncio.gather(app['match_task'],return_exceptions=True)

def clean_name(x): return str(x or 'RACER').strip()[:24] or 'RACER'
def integer(x, low, high, default):
    try: return max(low,min(high,int(x)))
    except (ValueError,TypeError,OverflowError): return default

def loadout(x):
    x=x if isinstance(x,dict) else {}
    return {k:str(x.get(k,''))[:100] for k in ('body','tire','glider','racer')} | {'drive': bool(x.get('drive',False))}

def lobby(r):
    return {'type':'lobby','code':r['code'],'host':r['host'],'members':[{'id':p['id'],'name':p['name'],'ready':p['ready'],'load':p['load']} for p in r['members'].values()], 'settings':r['settings'],'phase':r['phase']}

async def send(ws, data):
    if not ws.closed:
        try: await ws.send_json(data, dumps=lambda x:json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False))
        except (ConnectionError,RuntimeError,ValueError): pass

async def broadcast(r,data,exclude=None):
    await asyncio.gather(*(send(p['ws'],data) for p in list(r['members'].values()) if p['id']!=exclude),return_exceptions=True)

async def home(request): return web.FileResponse(ROOT/'index.html')
async def socket(request):
    # Prevent another website from opening the local server's WebSocket.
    origin=request.headers.get('Origin'); host=request.headers.get('Host')
    if origin and origin not in ('http://'+host,'https://'+host): raise web.HTTPForbidden(text='Origin mismatch')
    ws=web.WebSocketResponse(heartbeat=20,max_msg_size=512*1024); await ws.prepare(request)
    room=None; pid=None; last_input=0; last_snapshot=0; queued=None
    async def error(msg): await send(ws,{'type':'error','message':msg})
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT: continue
            try: d=json.loads(msg.data)
            except (ValueError,TypeError): continue
            if not isinstance(d,dict): continue
            t=d.get('type')
            if queued and queued.get('room'):
                room=queued['room'];pid=queued['id']
            if t=='match' and room is None and queued is None:
                kind=d.get('kind')
                if kind not in queues: continue
                token,account,rating=profile(d.get('token'),d.get('name'))
                if any(p['account']==account for q in queues.values() for p in q) or any(p.get('account')==account for r in rooms.values() if r['phase']=='race' for p in r['members'].values()): await error('すでに検索中です');continue
                queued={'ws':ws,'name':clean_name(d.get('name')),'load':loadout(d.get('load')),'account':account,'rating':rating,'queued':time.monotonic(),'rule': d.get('rule') if kind=='casual' and d.get('rule') in ONLINE_RULES else 'normal'}
                queues[kind].append(queued);await send(ws,{'type':'profile','token':token,'rating':rating});continue
            if t=='leave' and room is None: break
            if t in ('create','join') and room is None and queued is None:
                if t=='create':
                    if len(rooms)>=100: await error('サーバーが混雑中です');continue
                    code=str(secrets.randbelow(900000)+100000)
                    while code in rooms: code=str(secrets.randbelow(900000)+100000)
                    room={'code':code,'host':'p1','members':{},'phase':'lobby','settings':{'course':0,'cc':1,'level':1,'cpu':0,'rule':'normal','cup':0}}
                    rooms[code]=room
                else:
                    code=str(d.get('code','')).strip(); candidate=rooms.get(code)
                    if not candidate or candidate['phase']!='lobby' or len(candidate['members'])>=6:
                        await error('ルームがない、満員、またはレース中です');continue
                    room=candidate
                pid=next('p'+str(i) for i in range(1,7) if 'p'+str(i) not in room['members'])
                room['members'][pid]={'id':pid,'name':clean_name(d.get('name')),'load':loadout(d.get('load')),'ready':False,'ws':ws}
                await send(ws,{'type':'joined','id':pid,'code':room['code']});await broadcast(room,lobby(room));continue
            if room is None or room['members'].get(pid,{}).get('ws') is not ws: continue
            is_host=pid==room['host']; phase=room['phase']
            if t=='ready' and phase=='lobby':
                room['members'][pid]['ready']=bool(d.get('ready')); await broadcast(room,lobby(room))
            elif t=='settings' and is_host and phase=='lobby':
                room['settings']={'course':integer(d.get('course'),0,21,0),'cc':integer(d.get('cc'),0,3,1),'level':integer(d.get('level'),0,4,1),'cpu':integer(d.get('cpu'),0,6-len(room['members']),0),'rule':d.get('rule') if d.get('rule') in ONLINE_RULES else 'normal','cup':integer(d.get('cup'),0,len(GP_CUPS)-1,0)};await broadcast(room,lobby(room))
            elif t=='start' and is_host and phase=='lobby':
                if len(room['members'])<2: await error('友達が1人以上参加してから開始してください');continue
                if not all(p['ready'] for p in room['members'].values()): await error('全員が準備OKにしてください');continue
                room['settings']['cpu']=min(room['settings']['cpu'],6-len(room['members']));room['phase']='race'
                if room['settings'].get('rule')=='grandprix':
                    room['gp_round']=0;room['gp_scores']={p:0 for p in room['members']};room['settings']['course']=GP_CUPS[room['settings']['cup']][0]
                payload=lobby(room);payload['type']='start'
                if room['settings'].get('rule')=='grandprix': payload['gp']={'round':0,'cup':room['settings']['cup'],'scores':room['gp_scores']}
                await broadcast(room,payload)
            elif t=='input' and not is_host and phase=='race':
                now=time.monotonic()
                if now-last_input<.012: continue
                last_input=now; k=d.get('keys',{}); k=k if isinstance(k,dict) else {}; k={x:bool(k.get(x)) for x in ('ArrowUp','ArrowDown','ArrowLeft','ArrowRight','KeyX','KeyC','KeyV')}
                try: steer=float(d.get('steer',0)); steer=max(-1,min(1,steer)) if abs(steer)<=1 else 0
                except (ValueError,TypeError): steer=0
                await send(room['members'][room['host']]['ws'],{'type':'input','id':pid,'keys':k,'steer':steer,'drive':bool(d.get('drive'))})
            elif t=='snapshot' and is_host and phase=='race':
                now=time.monotonic()
                if now-last_snapshot<.025:continue
                last_snapshot=now
                state=d.get('state')
                if isinstance(state,dict): await broadcast(room,{'type':'snapshot','state':state},pid)
            elif t=='result' and is_host and phase=='race':
                rows=d.get('rows',[])
                if not isinstance(rows,list): continue
                changes=settle(room,rows) if room.get('kind')=='ranked' else None
                gp=None
                if room['settings'].get('rule')=='grandprix' and room.get('kind') is None:
                    # Server maintains aggregate points; never trust client-submitted totals.
                    ids=list(room['members'])
                    order=[x.get('id') for x in rows if isinstance(x,dict)]
                    if len(order)==len(set(order)) and set(ids).issubset(set(order)):
                        for i, racer_id in enumerate(order):
                            if racer_id in room['gp_scores']:room['gp_scores'][racer_id]+=GP_POINTS[min(i,len(GP_POINTS)-1)]
                    gp={'round':room['gp_round'],'cup':room['settings']['cup'],'scores':room['gp_scores'],'complete':room['gp_round']>=3}
                room['phase']='result';await broadcast(room,{'type':'result','rows':rows,'changes':changes,'gp':gp})
            elif t=='gp_next' and is_host and phase=='result' and room['settings'].get('rule')=='grandprix' and room.get('gp_round',3)<3:
                room['gp_round']+=1
                room['settings']['course']=GP_CUPS[room['settings']['cup']][room['gp_round']]
                room['phase']='race';payload=lobby(room);payload['type']='start'
                payload['gp']={'round':room['gp_round'],'cup':room['settings']['cup'],'scores':room['gp_scores']}
                await broadcast(room,payload)
            elif t=='leave': break
    finally:
        if queued:
            for q in queues.values():
                if queued in q:q.remove(queued)
            if queued.get('room'):room=queued['room'];pid=queued['id']
        if room and room['members'].get(pid,{}).get('ws') is ws:
            room['members'].pop(pid,None)
            if room.get('kind')=='ranked' and room['phase']=='race': room['quit'].add(pid)
            if pid==room['host']:
                if room.get('kind')=='ranked' and room['phase']=='race':
                    with db() as c:
                        query(c,'UPDATE players SET rating=CASE WHEN rating>=20 THEN rating-20 ELSE 0 END,games=games+1 WHERE id=?',(room['rank_members'][pid]['account'],))
                await broadcast(room,{'type':'closed','message':'ホストが退出したためルームは終了しました。'})
                for p in list(room['members'].values()): await p['ws'].close()
                rooms.pop(room['code'],None)
            elif room['phase']=='lobby':
                room['settings']['cpu']=min(room['settings']['cpu'],6-len(room['members']));await broadcast(room,lobby(room))
            else: await broadcast(room,{'type':'departed','id':pid})
    return ws


# Time attack beta: single-use server ticket with elapsed-time sanity check.
trial_tickets={}
def trial_identity(token):
    if not isinstance(token,str) or len(token)!=64 or any(x not in '0123456789abcdef' for x in token): return None
    return hashlib.sha256(token.encode()).hexdigest()
async def trial_start(request):
    d=await request.json(); c=d.get('course'); cc=d.get('cc')
    if type(c) is not int or not 0<=c<22 or type(cc) is not int or not 0<=cc<4: raise web.HTTPBadRequest()
    token,account,_=profile(d.get('token'),d.get('name'))
    now=time.monotonic()
    for k,v in list(trial_tickets.items()):
        if now-v[3]>7200 or v[0]==account: trial_tickets.pop(k,None)
    if len(trial_tickets)>=5000: raise web.HTTPServiceUnavailable()
    ticket=secrets.token_hex(24);trial_tickets[ticket]=(account,c,cc,now)
    return web.json_response({'ticket':ticket,'token':token})
async def trial_finish(request):
    d=await request.json(); account=trial_identity(d.get('token')); ticket=d.get('ticket'); t=d.get('time')
    if not isinstance(ticket,str) or not account or not isinstance(t,(int,float)) or not math.isfinite(t) or not 10<=t<=7200: raise web.HTTPBadRequest()
    v=trial_tickets.get(ticket)
    if not v or v[0]!=account or time.monotonic()-v[3]+.5<t or time.monotonic()-v[3]>7200: raise web.HTTPBadRequest(text='Invalid trial ticket')
    trial_tickets.pop(ticket,None);_,c,cc,_=v; ms=round(t*1000)
    with db() as conn:
        query(conn,'INSERT INTO trial_records(account,course,cc,name,ms) VALUES (?,?,?,?,?) ON CONFLICT(account,course,cc) DO UPDATE SET name=excluded.name,ms=excluded.ms WHERE excluded.ms<trial_records.ms',(account,c,cc,clean_name(d.get('name')),ms))
        best=query(conn,'SELECT ms FROM trial_records WHERE account=? AND course=? AND cc=?',(account,c,cc)).fetchone()[0]
        place=1+query(conn,'SELECT COUNT(*) FROM trial_records WHERE course=? AND cc=? AND (ms<? OR (ms=? AND account<?))',(c,cc,best,best,account)).fetchone()[0]
    return web.json_response({'ok':True,'place':place,'best':best/1000})
async def trial_name(request):
    d=await request.json(); account=trial_identity(d.get('token'))
    if not account: raise web.HTTPBadRequest()
    with db() as conn:
        query(conn,'UPDATE trial_records SET name=? WHERE account=?',(clean_name(d.get('name')),account))
        query(conn,'UPDATE players SET name=? WHERE id=?',(clean_name(d.get('name')),account))
    return web.json_response({'ok':True})
async def trial_ranking(request):
    try: c=int(request.query['course']);cc=int(request.query['cc']);assert 0<=c<22 and 0<=cc<4
    except (ValueError,KeyError,AssertionError): raise web.HTTPBadRequest()
    with db() as conn:
        rows=query(conn,'SELECT name,ms FROM trial_records WHERE course=? AND cc=? ORDER BY ms,account LIMIT 3',(c,cc)).fetchall()
    return web.json_response({'rows':[{'name':r[0],'time':r[1]/1000} for r in rows],'persistent':bool(DBURL)})

app=web.Application(client_max_size=512*1024);app.router.add_get('/',home);app.router.add_get('/ws',socket);app.router.add_get('/ranking',ranking);app.router.add_get('/presence',presence);app.router.add_post('/trial/start',trial_start);app.router.add_post('/trial/finish',trial_finish);app.router.add_post('/trial/name',trial_name);app.router.add_get('/trial/ranking',trial_ranking);app.on_startup.append(startup);app.on_cleanup.append(cleanup)
if __name__=='__main__': web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT',8765)))
