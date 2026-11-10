/* Equity Intelligence · modo noche / modo claro. Solo guarda tu elección en tu propio navegador. */
(function(){
  var K="ei-tema",R=document.documentElement;
  function leer(){try{return localStorage.getItem(K)}catch(e){return null}}
  function guardar(v){try{localStorage.setItem(K,v)}catch(e){}}
  function aplicar(t){
    if(t==="light")R.setAttribute("data-theme","light");else R.removeAttribute("data-theme");
    var b=document.querySelectorAll("[data-tema-btn]");
    for(var i=0;i<b.length;i++)b[i].textContent=t==="light"?"🌙 Modo noche":"☀ Modo claro";
  }
  window.temaActual=function(){return R.getAttribute("data-theme")==="light"?"light":"dark"};
  window.cambiarTema=function(){
    var n=window.temaActual()==="light"?"dark":"light";
    guardar(n);aplicar(n);
    try{window.dispatchEvent(new Event("tema"))}catch(e){}
  };
  aplicar(leer()==="light"?"light":"dark");
  document.addEventListener("DOMContentLoaded",function(){aplicar(window.temaActual())});
})();
