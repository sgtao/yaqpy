/*
 * yaqpy Web 版：ブラウザへのファイルのドラッグ＆ドロップ（v0.7.0）。
 *
 * Flet の標準の Web クライアントには、ファイルのドロップを受ける部品が無い。そこで、
 *   1. ページ全体で dragover / drop を受け、ドロップされた File を手元（stash）に取っておく
 *   2. 「ドロップがあった」ことを、ブラウザの URL（ルート）の変更として Python 側へ知らせる
 *      （Flet の page.on_route_change が受ける）
 *   3. Python 側が、いつもの「ファイルを追加」（FilePicker.pick_files）を呼ぶ。Flutter の
 *      file_picker は <input type="file"> の click() でダイアログを開くので、その click() を
 *      差し替えて、ダイアログの代わりに stash の File を「選んだこと」にする
 * という順で、既存のアップロードの経路（サイズの事前確認・進捗・上限）にそのまま合流させる。
 *
 * stash は DROP_TTL_MS のあいだだけ有効。Python が受け取らなかった（通知が届かない等の）ときに、
 * あとから利用者が押した「ファイルを追加」に古いドロップが混ざらないようにする。
 */
(function () {
  "use strict";

  var DROP_ROUTE = "__yaqpy_drop";
  var DROP_TTL_MS = 10000;
  var stash = null;
  var timer = null;

  function hasFiles(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    if (!types) return false;
    for (var i = 0; i < types.length; i++) {
      if (types[i] === "Files") return true;
    }
    return false;
  }

  function clearStash() {
    stash = null;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  // ドロップを許す（既定の動作は「ファイルをブラウザで開く」）
  document.addEventListener("dragover", function (event) {
    if (hasFiles(event)) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    }
  }, true);

  document.addEventListener("drop", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    var files = Array.prototype.slice.call(event.dataTransfer.files || []);
    if (files.length === 0) return;
    clearStash();
    stash = files;
    timer = setTimeout(clearStash, DROP_TTL_MS);
    // Python 側への通知：ルートを変えて popstate を起こす（Flet のルーターが拾う）
    var url = new URL(DROP_ROUTE, document.baseURI);
    history.pushState(null, "", url.pathname);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, true);

  // file_picker の <input type="file">.click() を、stash があるときだけ差し替える
  var originalClick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function () {
    if (this.type === "file" && stash !== null) {
      var files = stash;
      clearStash();
      var transfer = new DataTransfer();
      files.forEach(function (file) { transfer.items.add(file); });
      var input = this;
      input.files = transfer.files;
      setTimeout(function () {
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }, 0);
      return;
    }
    return originalClick.apply(this, arguments);
  };
})();
