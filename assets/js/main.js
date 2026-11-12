// アプリ内ブラウザ（LINE / Instagram / X など）では buzz アプリへ遷移できないため、
// 該当する場合のみ警告バナーを表示する
const IN_APP_BROWSER = /Line\/|FBAN|FBAV|Instagram|Twitter|MicroMessenger|KAKAOTALK|; wv\)/i;

if (IN_APP_BROWSER.test(navigator.userAgent)) {
  document.getElementById("inapp-warning")?.removeAttribute("hidden");
}

// #join-pc へのアンカー遷移時に折りたたみを自動で開く
const openJoinPc = () => {
  if (location.hash === "#join-pc") {
    document.getElementById("join-pc")?.setAttribute("open", "");
  }
};
openJoinPc();
addEventListener("hashchange", openJoinPc);

// 招待リンクをコピーする。アプリ導入中にページを離れても戻れるようにするための導線
const copyText = async (text) => {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // 非セキュアコンテキストや古いブラウザ向けのフォールバック
  const ta = Object.assign(document.createElement("textarea"), { value: text });
  document.body.append(ta);
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  if (!ok) throw new Error("copy failed");
};

document.querySelectorAll("[data-copy-invite]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const status = btn.parentElement.querySelector(".copy-status");
    const url = btn.closest(".cta-container")?.querySelector(".btn-primary")?.href;
    try {
      if (!url) throw new Error("invite url not found");
      await copyText(url);
      status.textContent = "コピーしました";
    } catch {
      status.textContent = "コピーできませんでした。上のボタンを長押ししてリンクをコピーしてください";
    }
  });
});
