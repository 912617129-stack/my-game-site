
const categoryData = [
  {
    id: "action",
    name: "アクション",
    emoji: "⚔️",
    games: ["ヒーローアドベンチャー","忍者ランナー","モンスターバトル","スカイジャンプ","ダンジョンファイト","スーパーアタック","ドラゴンハンター","シャドウファイター","タワーディフェンス","エピックウォリアー"]
  },
  {
    id: "racing",
    name: "レース",
    emoji: "🏎️",
    games: ["スーパーカーレース","ドリフトチャレンジ","ターボレーサー","オフロードレース","バイクレーシング","スピードスター","シティドライブ","フォーミュラレーサー","モンスタートラック","ハイウェイレーサー"]
  },
  {
    id: "puzzle",
    name: "パズル",
    emoji: "🧩",
    games: ["ブロックマスター","マッチパズル","カラーコネクト","ナンバーパズル","宝石パズル","マジックキューブ","ボールソート","ロジックチャレンジ","タイルパズル","脳トレマスター"]
  },
  {
    id: "shooting",
    name: "シューティング",
    emoji: "🚀",
    games: ["スペースシューター","ゾンビディフェンス","バトルアリーナ","ギャラクシーアタック","スナイパーチャレンジ","エイリアンハンター","タンクバトル","ネオンシューター","ロボットウォーズ","スペースガーディアン"]
  },
  {
    id: "adventure",
    name: "冒険",
    emoji: "🗺️",
    games: ["ジャングルクエスト","失われた島","トレジャーハンター","ミステリーランド","マジックフォレスト","海賊の冒険","スカイアイランド","古代遺跡の謎","サバイバルアイランド","クリスタルクエスト"]
  },
  {
    id: "rpg",
    name: "RPG",
    emoji: "🏰",
    games: ["ファンタジークエスト","ドラゴンレジェンド","勇者の旅","マジックキングダム","ソードマスター","モンスタークロニクル","エレメントヒーローズ","キングダムバトル","レジェンドオブナイト","ミスティックワールド"]
  },
  {
    id: "sports",
    name: "スポーツ",
    emoji: "⚽",
    games: ["ストリートサッカー","バスケットチャレンジ","テニスマスター","ボウリングキング","ゴルフアドベンチャー","バレーボールスター","卓球チャンピオン","スケートボード","ベースボールヒーロー","フットボールスター"]
  },
  {
    id: "horror",
    name: "ホラー",
    emoji: "👻",
    games: ["ダークハウス","ホーンテッドスクール","ナイトサバイバル","ミステリーマンション","シャドウホール","ゴーストハンター","廃病院の謎","ミッドナイト","恐怖の森","ダークエスケープ"]
  },
  {
    id: "simulation",
    name: "シミュレーション",
    emoji: "🏗️",
    games: ["シティビルダー","ファームライフ","レストランマスター","ペットワールド","テーマパーク","マイドリームハウス","アイランドライフ","ショップマネージャー","ファクトリーキング","ホテルストーリー"]
  },
  {
    id: "casual",
    name: "カジュアル",
    emoji: "🎲",
    games: ["スライムジャンプ","フルーツキャッチ","ボールバウンス","カラフルランナー","ペンギンジャンプ","マジックボール","スイートキャンディ","リラックスゲーム","ワンタップチャレンジ","ハッピーパーク"]
  }
];

// 100個のゲームカタログを作成
// 実際のゲームURLは、掲載許可を確認してから登録します
const games = categoryData.flatMap((category, categoryIndex) =>
  category.games.map((name, index) => ({
    id: category.id + "-" + (index + 1),
    name,
    category: category.id,
    categoryName: category.name,
    emoji: category.emoji,
    number: categoryIndex * 10 + index + 1,
    embedUrl: "",
    description: category.name + "のゲーム",
    popular: index < 3 && categoryIndex < 4
  }))
);

const categoryColors = {
  action: "#ffe2dc",
  racing: "#dceeff",
  puzzle: "#f0e3ff",
  shooting: "#dce5ff",
  adventure: "#ddf3e4",
  rpg: "#ffe8ce",
  sports: "#dff4e8",
  horror: "#e7e0ee",
  simulation: "#fff0d7",
  casual: "#ffe1ed"
};

let selectedCategory = "all";
let searchWord = "";
let favorites = [];

try {
  favorites = JSON.parse(
    localStorage.getItem("gamepark-favorites") || "[]"
  );
} catch {
  favorites = [];
}

const gameGrid = document.getElementById("gameGrid");
const popularGames = document.getElementById("popularGames");
const favoriteGames = document.getElementById("favoriteGames");
const gameCount = document.getElementById("gameCount");
const emptyMessage = document.getElementById("emptyMessage");
const gameModal = document.getElementById("gameModal");
const gameFrame = document.getElementById("gameFrame");
const gameTitle = document.getElementById("gameTitle");

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function createCard(game) {
  const favorite = favorites.includes(game.id);

  return `
    <article class="game-card" data-id="${game.id}">
      <button class="favorite-button ${favorite ? "active" : ""}"
        data-favorite="${game.id}"
        aria-label="お気に入り">
        ${favorite ? "♥" : "♡"}
      </button>

      <div class="game-image"
        style="background:${categoryColors[game.category]}">
        ${game.emoji}
      </div>

      <div class="game-info">
        <h3>${escapeHTML(game.name)}</h3>
        <p>${escapeHTML(game.description)}</p>
        <span class="game-tag">
          ${escapeHTML(game.categoryName)}
        </span>
      </div>
    </article>
  `;
}

function renderGames() {
  const filtered = games.filter(game => {
    const matchesCategory =
      selectedCategory === "all" ||
      game.category === selectedCategory;

    const matchesSearch =
      game.name.toLowerCase().includes(searchWord) ||
      game.categoryName.toLowerCase().includes(searchWord);

    return matchesCategory && matchesSearch;
  });

  gameGrid.innerHTML = filtered.map(createCard).join("");

  gameCount.textContent = filtered.length + " GAMES";

  emptyMessage.hidden = filtered.length !== 0;

  popularGames.innerHTML = games
    .filter(game => game.popular)
    .slice(0, 10)
    .map(createCard)
    .join("");

  const favoriteList = games.filter(game =>
    favorites.includes(game.id)
  );

  favoriteGames.innerHTML = favoriteList
    .map(createCard)
    .join("");
}

// カテゴリー選択
document.querySelectorAll(".category").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".category")
      .forEach(item => item.classList.remove("active"));

    button.classList.add("active");
    selectedCategory = button.dataset.category;
    renderGames();
  });
});

// 検索
document.getElementById("searchInput")
  .addEventListener("input", event => {
    searchWord = event.target.value.trim().toLowerCase();
    renderGames();
  });

// お気に入りとゲーム起動
document.addEventListener("click", event => {
  const favoriteButton = event.target.closest("[data-favorite]");

  if (favoriteButton) {
    const id = favoriteButton.dataset.favorite;

    if (favorites.includes(id)) {
      favorites = favorites.filter(item => item !== id);
    } else {
      favorites.push(id);
    }

    localStorage.setItem(
      "gamepark-favorites",
      JSON.stringify(favorites)
    );

    renderGames();
    return;
  }

  const card = event.target.closest(".game-card");

  if (card) {
    const game = games.find(
      item => item.id === card.dataset.id
    );

    if (game) openGame(game);
  }
});

// ゲーム画面
function openGame(game) {
  gameTitle.textContent = game.name;

  if (game.embedUrl) {
    gameFrame.removeAttribute("srcdoc");
    gameFrame.src = game.embedUrl;
  } else {
    gameFrame.removeAttribute("src");
    gameFrame.srcdoc = `
      <html>
      <body style="
        margin:0;
        background:#171724;
        color:white;
        font-family:Arial,sans-serif;
        display:grid;
        place-items:center;
        height:100vh;
        text-align:center;">
        <div>
          <div style="font-size:65px">${game.emoji}</div>
          <h2>${escapeHTML(game.name)}</h2>
          <p>このゲームは掲載準備中です。</p>
          <p>利用許可のあるゲームを順番に追加します。</p>
        </div>
      </body>
      </html>
    `;
  }

  gameModal.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeGame() {
  gameModal.hidden = true;
  gameFrame.removeAttribute("src");
  gameFrame.removeAttribute("srcdoc");
  document.body.style.overflow = "";
}

document.getElementById("closeGame")
  .addEventListener("click", closeGame);

gameModal.addEventListener("click", event => {
  if (event.target === gameModal) closeGame();
});

document.getElementById("fullscreenButton")
  .addEventListener("click", () => {
    if (gameFrame.requestFullscreen) {
      gameFrame.requestFullscreen();
    }
  });

document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !gameModal.hidden) {
    closeGame();
  }
});

// 最初の表示
renderGames();

console.log("GAME PARK: " + games.length + " games registered");
