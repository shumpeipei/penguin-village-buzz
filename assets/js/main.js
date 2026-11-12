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
