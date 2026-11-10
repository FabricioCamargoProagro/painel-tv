/*
 * Tema de Natal do painel da TV — camada POR CIMA do visual original (não mexe em nada dele).
 * Liga/desliga em tema.js (window.TEMA_ATIVO = 'natal' | 'original'); para testar: ?tema=natal / ?tema=original.
 *   - gorro do Papai Noel no "P" de PROAGRO, na marca do cabeçalho;
 *   - cordão de luzinhas piscando no alto da tela (na margem, acima do cabeçalho);
 *   - neve fina e translúcida (não atrapalha a leitura dos números);
 *   - de 3 em 3 minutos o trenó do Papai Noel atravessa o cabeçalho puxando a faixa "Boas Festas!"
 *     (a 1ª passada vem ~10 s depois de abrir).
 * Tudo em SVG/CSS, sem imagem externa; só transform/opacity animados (leve para a TV).
 * ?natal=demo deixa o trenó parado no meio da tela (para tirar foto da prévia).
 */
(function () {
  'use strict';
  const palco = document.getElementById('palco');
  if (!palco || document.getElementById('natal-css')) return;
  const P = new URLSearchParams(location.search);
  const DEMO = P.get('natal') === 'demo';
  const ES = /^es/i.test(P.get('lang') || '');
  const CICLO = 180;                                   // segundos entre passadas do trenó
  const r = (a, b) => a + Math.random() * (b - a);

  /* ---------------- estilos ---------------- */
  const css = document.createElement('style');
  css.id = 'natal-css';
  css.textContent = `
    #palco{overflow:hidden}
    .natal{position:absolute;pointer-events:none}
    header{position:relative}
    .natal-gorro{left:43px;top:-22px;width:44px;height:36px;z-index:46;transform:rotate(-16deg);transform-origin:30% 90%;
      filter:drop-shadow(0 2px 2px rgba(0,0,0,.45))}
    .natal-luzes{left:0;top:0;width:1920px;height:34px;z-index:45}
    .natal-luzes .brilho{animation:piscar 2.4s ease-in-out infinite alternate}
    .natal-luzes .lamp{animation:acender 2.4s ease-in-out infinite alternate}
    @keyframes piscar{from{opacity:.15}to{opacity:.85}}
    @keyframes acender{from{opacity:.55}to{opacity:1}}
    .natal-neve{inset:0;z-index:40}
    .natal-neve i{position:absolute;top:-16px;display:block;animation:cair var(--t) linear var(--d) infinite}
    .natal-neve i::after{content:"";display:block;width:var(--s);height:var(--s);border-radius:50%;background:#fff;opacity:var(--o);
      box-shadow:0 0 4px rgba(255,255,255,.6);animation:balancar var(--b) ease-in-out var(--d) infinite alternate}
    @keyframes cair{from{transform:translateY(0)}to{transform:translateY(1110px)}}
    @keyframes balancar{from{transform:translateX(calc(var(--dx) * -1))}to{transform:translateX(var(--dx))}}
    .natal-treno{left:0;top:2px;width:680px;height:99px;z-index:50;transform:translateX(2000px);
      animation:voar ${CICLO}s linear ${-CICLO * 0.94}s infinite}
    .natal-treno svg{display:block;width:680px;height:99px;animation:sacudir 1.4s ease-in-out infinite alternate}
    @keyframes voar{0%{transform:translateX(2000px)}9%{transform:translateX(-740px)}100%{transform:translateX(-740px)}}
    @keyframes sacudir{from{transform:translateY(-5px) rotate(-1.2deg)}to{transform:translateY(5px) rotate(1.2deg)}}
    .natal-treno .estrela{animation:piscar 0.9s ease-in-out infinite alternate}
    .natal-treno .nariz{animation:piscar 0.7s ease-in-out infinite alternate}
    @media (prefers-reduced-motion: reduce){.natal *, .natal{animation:none !important}}
  `;
  document.head.appendChild(css);

  /* ---------------- gorro na marca ---------------- */
  const header = palco.querySelector('header');
  if (header) {
    header.insertAdjacentHTML('beforeend', `
      <svg class="natal natal-gorro" viewBox="0 0 100 82" aria-hidden="true">
        <path d="M14 60 C20 24 46 4 76 14 C88 18 95 30 93 44 C86 36 78 33 71 35 C75 43 79 51 82 60 Z" fill="#d7263d"/>
        <path d="M71 35 C75 43 79 51 82 60 L70 60 C68 50 66 42 63 36 Z" fill="#a3162a" opacity=".55"/>
        <path d="M28 40 C36 24 52 14 68 16" fill="none" stroke="#ff6b7a" stroke-width="3" stroke-linecap="round" opacity=".55"/>
        <circle cx="92" cy="47" r="9.5" fill="#f5f7f4"/>
        <rect x="5" y="55" width="86" height="19" rx="9.5" fill="#f5f7f4"/>
        <path d="M12 64 h70" stroke="#dfe4e0" stroke-width="3" stroke-linecap="round" opacity=".9"/>
      </svg>`);
  }

  /* ---------------- luzinhas ---------------- */
  const cores = ['#ff4d5a', '#ffd24d', '#4fd67b', '#6cc6ff', '#ff9a3d'];
  let fio = 'M0 3', lampadas = '', defs = '';
  cores.forEach((c, i) => { defs += `<radialGradient id="ng${i}"><stop offset="0" stop-color="${c}" stop-opacity=".95"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient>`; });
  for (let k = 0; k < 20; k++) {
    const x0 = k * 96, xm = x0 + 48, x1 = x0 + 96;
    fio += ` Q${xm} 17 ${x1} 3`;
    const c = k % cores.length, atraso = (-r(0, 2.4)).toFixed(2);
    lampadas += `
      <circle class="brilho" cx="${xm}" cy="22" r="15" fill="url(#ng${c})" style="animation-delay:${atraso}s"/>
      <rect x="${xm - 3}" y="10" width="6" height="5" rx="1.5" fill="#2b3a31"/>
      <ellipse class="lamp" cx="${xm}" cy="21" rx="5" ry="7.5" fill="${cores[c]}" style="animation-delay:${atraso}s"/>
      <ellipse cx="${xm - 1.6}" cy="18" rx="1.6" ry="2.6" fill="#fff" opacity=".7"/>`;
  }
  palco.insertAdjacentHTML('beforeend', `
    <svg class="natal natal-luzes" viewBox="0 0 1920 34" aria-hidden="true">
      <defs>${defs}</defs>
      <path d="${fio}" fill="none" stroke="#1d2b23" stroke-width="2.2"/>
      ${lampadas}
    </svg>`);

  /* ---------------- neve ---------------- */
  let flocos = '';
  for (let k = 0; k < 46; k++) {
    flocos += `<i style="left:${r(0, 1920).toFixed(0)}px;--t:${r(15, 30).toFixed(1)}s;--d:${(-r(0, 30)).toFixed(1)}s;` +
              `--s:${r(2, 5.5).toFixed(1)}px;--o:${r(0.35, 0.75).toFixed(2)};--b:${r(3, 6).toFixed(1)}s;--dx:${r(10, 34).toFixed(0)}px"></i>`;
  }
  palco.insertAdjacentHTML('beforeend', `<div class="natal natal-neve" aria-hidden="true">${flocos}</div>`);

  /* ---------------- trenó ---------------- */
  const faixa = ES ? '¡Felices Fiestas! · ProAgro Seguros' : 'Boas Festas! · ProAgro Seguros';
  const rena = (x, y, rudolph) => `
    <g transform="translate(${x} ${y})">
      <path d="M22 26 L28 10 L23 2 M28 10 L37 6 M16 26 L13 11 L6 5 M13 11 L19 4" stroke="#c9a26b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M44 68 L35 90 M54 70 L50 94 M76 69 L86 90 M86 66 L98 84" stroke="#6e4524" stroke-width="5" stroke-linecap="round"/>
      <ellipse cx="64" cy="56" rx="35" ry="15" fill="#9b6a3c"/>
      <path d="M36 50 C30 42 26 36 24 32" stroke="#9b6a3c" stroke-width="12" stroke-linecap="round"/>
      <circle cx="21" cy="32" r="10.5" fill="#9b6a3c"/>
      <ellipse cx="11" cy="37" rx="8" ry="5.5" fill="#a87849"/>
      <ellipse cx="27" cy="25" rx="5" ry="2.6" fill="#7a4f2a" transform="rotate(-35 27 25)"/>
      <circle cx="19" cy="29" r="2" fill="#1b130c"/>
      <path d="M98 50 q8 -6 4 -12" stroke="#f3e6d3" stroke-width="5" stroke-linecap="round"/>
      <path d="M40 52 C52 60 74 60 92 50" stroke="#d7263d" stroke-width="4" fill="none"/>
      <circle cx="66" cy="59" r="3.2" fill="#ffd24d"/>
      ${rudolph ? `<circle class="nariz" cx="3" cy="37" r="9" fill="url(#ngnariz)"/><circle cx="3" cy="37" r="4.6" fill="#ff3b3b"/>`
                : `<circle cx="3" cy="37" r="3.6" fill="#2a1b10"/>`}
    </g>`;
  let estrelas = '';
  for (let k = 0; k < 9; k++) {
    const x = 700 + k * 11 + r(-4, 4), y = 44 + Math.sin(k * 0.9) * 14, s = r(2.5, 5.5);
    estrelas += `<path class="estrela" d="M${x} ${y - s} L${x + s * 0.3} ${y - s * 0.3} L${x + s} ${y} L${x + s * 0.3} ${y + s * 0.3} L${x} ${y + s} L${x - s * 0.3} ${y + s * 0.3} L${x - s} ${y} L${x - s * 0.3} ${y - s * 0.3} Z" fill="#ffe27a" style="animation-delay:${(-r(0, 0.9)).toFixed(2)}s"/>`;
  }
  palco.insertAdjacentHTML('beforeend', `
    <div class="natal natal-treno" aria-hidden="true">
      <svg viewBox="0 0 800 116" width="800" height="116">
        <defs><radialGradient id="ngnariz"><stop offset="0" stop-color="#ff5a5a" stop-opacity=".9"/><stop offset="1" stop-color="#ff5a5a" stop-opacity="0"/></radialGradient></defs>
        ${rena(0, 6, true)}${rena(122, 12, false)}
        <path d="M96 58 C150 46 190 52 236 60 L300 66" stroke="#e8b931" stroke-width="2.5" fill="none"/>
        <path d="M218 62 C246 56 272 58 300 64" stroke="#e8b931" stroke-width="2.5" fill="none"/>
        <ellipse cx="404" cy="40" rx="24" ry="20" fill="#7a5a32"/>
        <path d="M392 24 q12 -10 24 0" stroke="#5c4223" stroke-width="4" fill="none"/>
        <rect x="396" y="30" width="16" height="14" rx="2" fill="#4fd67b"/><rect x="402" y="30" width="4" height="14" fill="#ffd24d"/>
        <ellipse cx="360" cy="40" rx="23" ry="21" fill="#d7263d"/>
        <rect x="338" y="44" width="44" height="7" fill="#1b130c"/><rect x="356" y="43" width="9" height="9" rx="1.5" fill="#e8b931"/>
        <path d="M374 34 L392 12" stroke="#d7263d" stroke-width="9" stroke-linecap="round"/>
        <circle cx="393" cy="10" r="6" fill="#f5f7f4"/>
        <circle cx="352" cy="14" r="11" fill="#f1c7a5"/>
        <path d="M341 16 C340 30 348 36 354 36 C360 36 366 30 364 16 Z" fill="#f5f7f4"/>
        <circle cx="349" cy="12" r="1.6" fill="#1b130c"/><circle cx="345" cy="17" r="3" fill="#f2a490"/>
        <path d="M340 9 C342 -6 360 -8 368 2 L366 8 Z" fill="#d7263d"/>
        <rect x="338" y="5" width="30" height="7" rx="3.5" fill="#f5f7f4"/>
        <circle cx="370" cy="1" r="4.5" fill="#f5f7f4"/>
        <path d="M296 44 L414 44 Q434 44 432 64 L428 76 Q426 84 416 84 L308 84 Q292 84 294 68 Z" fill="#c81e2c"/>
        <path d="M300 52 L428 52" stroke="#e8b931" stroke-width="3"/>
        <path d="M318 84 L312 98 M408 84 L414 98" stroke="#e8b931" stroke-width="4"/>
        <path d="M284 100 L420 100 Q444 100 446 84" stroke="#e8b931" stroke-width="5" fill="none" stroke-linecap="round"/>
        <path d="M432 58 C452 54 466 52 484 52" stroke="#f5f7f4" stroke-width="1.6" stroke-dasharray="4 3" fill="none"/>
        <rect x="484" y="34" width="300" height="36" rx="7" fill="#f5f7f4"/>
        <path d="M784 40 l14 -6 l-6 16 l6 16 l-14 -6 Z" fill="#e3e8e4"/>
        <text x="634" y="58.5" text-anchor="middle" font-family="Roboto,'Segoe UI',system-ui,Arial,sans-serif" font-size="19"
              font-weight="800" fill="#c81e2c">${faixa}</text>
        ${estrelas}
      </svg>
    </div>`);

  if (DEMO) {                                          // prévia: trenó parado no meio da tela, neve congelada
    const t = palco.querySelector('.natal-treno');
    t.style.animation = 'none';
    t.style.transform = 'translateX(560px)';
    palco.querySelectorAll('.natal-neve i, .natal-neve i::after').forEach(e => { e.style.animationPlayState = 'paused'; });
  }
})();
