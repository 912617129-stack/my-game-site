# GAME PARK おすすめ表示修正版

本格化おすすめ欄の表示処理をより堅牢に修正しました。
- おすすめ9タイトルをIDで明示的に取得
- 表示先が存在するか確認してから描画
- おすすめ欄とカードの表示をCSSで明示
- `games.js?v=featured5` に変更し、ブラウザの古いJavaScriptキャッシュを回避しやすくしました

## 更新方法
ZIPを解凍し、`index.html` `style.css` `games.js` の3ファイルをGitHubリポジトリの同名ファイルに上書きしてください。
GitHub Pages反映後、Windows/Chromebookなら `Ctrl + Shift + R` で強制再読み込みしてください。
