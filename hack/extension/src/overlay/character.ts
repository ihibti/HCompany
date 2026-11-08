// The tomato-farmer — "cartoon 3D doux": gradient volumes, clay palette, no outlines.

export const CHAR_SVG = `
<svg viewBox="0 0 120 140" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <radialGradient id="gSkin" cx="38%" cy="30%" r="75%">
      <stop offset="0%" stop-color="#ffd9ae"/><stop offset="60%" stop-color="#f5b76b"/><stop offset="100%" stop-color="#d68f4a"/>
    </radialGradient>
    <radialGradient id="gTom" cx="35%" cy="28%" r="78%">
      <stop offset="0%" stop-color="#ff7a68"/><stop offset="55%" stop-color="#d63031"/><stop offset="100%" stop-color="#a02222"/>
    </radialGradient>
    <linearGradient id="gDenim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#5d7fa6"/><stop offset="100%" stop-color="#3d5a76"/>
    </linearGradient>
    <radialGradient id="gHat" cx="42%" cy="30%" r="80%">
      <stop offset="0%" stop-color="#f4dd95"/><stop offset="70%" stop-color="#e0b84f"/><stop offset="100%" stop-color="#b98f2e"/>
    </radialGradient>
    <linearGradient id="gBasket" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#b5814e"/><stop offset="100%" stop-color="#8a5a2b"/>
    </linearGradient>
    <radialGradient id="gEye" cx="40%" cy="35%" r="70%">
      <stop offset="0%" stop-color="#ffffff"/><stop offset="80%" stop-color="#f2ece2"/><stop offset="100%" stop-color="#d8d0c2"/>
    </radialGradient>
    <radialGradient id="gCheek" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#f0947f" stop-opacity=".9"/><stop offset="100%" stop-color="#f0947f" stop-opacity="0"/>
    </radialGradient>
    <filter id="fSoft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="1.2"/></filter>
    <pattern id="pWeave" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(30)">
      <rect width="6" height="6" fill="#e0b84f"/><path d="M0 3h6" stroke="#c49a3a" stroke-width=".8"/>
    </pattern>
  </defs>
  <ellipse class="c-shadow" cx="60" cy="132" rx="30" ry="6.5" fill="rgba(60,40,20,.28)" filter="url(#fSoft)"/>
  <g class="c-body-all" style="transform-origin:60px 118px">
    <g class="c-legs">
      <path d="M45 112 l-4 15 M75 112 l4 15" stroke="#3d5a76" stroke-width="8" stroke-linecap="round"/>
      <ellipse cx="39" cy="128" rx="8" ry="4" fill="#7a5a40"/>
      <ellipse cx="81" cy="128" rx="8" ry="4" fill="#7a5a40"/>
    </g>
    <g class="c-torso" style="transform-origin:60px 104px">
      <rect x="37" y="80" width="46" height="36" rx="11" fill="url(#gDenim)"/>
      <rect x="37" y="80" width="46" height="11" rx="5.5" fill="#33485e"/>
      <rect x="50" y="94" width="20" height="15" rx="3.5" fill="#33485e"/>
      <path d="M50 97 h20 M50 103 h20" stroke="#8fb0d4" stroke-width="1" stroke-dasharray="2.5 2"/>
      <circle cx="54" cy="97.5" r="1.8" fill="#d9d9d9"/><circle cx="66" cy="97.5" r="1.8" fill="#d9d9d9"/>
      <path d="M37 84 q-3 14 2 28" stroke="rgba(0,0,0,.18)" stroke-width="3" fill="none" filter="url(#fSoft)"/>
    </g>
    <g class="c-arm-l" style="transform-origin:36px 86px">
      <path d="M36 86 q-13 3 -14 15" stroke="#d68f4a" stroke-width="9" fill="none" stroke-linecap="round"/>
      <path d="M36 86 q-13 3 -14 15" stroke="url(#gSkin)" stroke-width="7" fill="none" stroke-linecap="round"/>
      <circle cx="22" cy="102" r="5.6" fill="url(#gSkin)"/>
    </g>
    <g class="c-arm-r" style="transform-origin:84px 86px">
      <path d="M84 86 q15 -4 16 -17" stroke="#d68f4a" stroke-width="9" fill="none" stroke-linecap="round"/>
      <path d="M84 86 q15 -4 16 -17" stroke="url(#gSkin)" stroke-width="7" fill="none" stroke-linecap="round"/>
      <circle cx="101" cy="67" r="5.6" fill="url(#gSkin)"/>
      <g class="c-held" style="transform-origin:101px 57px">
        <circle cx="101" cy="57" r="9" fill="url(#gTom)"/>
        <ellipse cx="98" cy="54" rx="3" ry="2" fill="#ff9d8f" opacity=".8"/>
        <path d="M101 48 l-2.5 -3.5 M101 48 l2.5 -3.5 M101 48 l-4.5 -.8 M101 48 l4.5 -.8 M101 48 v-4" stroke="#2e9e57" stroke-width="1.6" stroke-linecap="round"/>
      </g>
    </g>
    <g class="c-head" style="transform-origin:60px 52px">
      <circle cx="60" cy="52" r="27" fill="url(#gSkin)"/>
      <path d="M33 52 a27 27 0 0 0 54 0" fill="none" stroke="#d68f4a" stroke-width="1" opacity=".5"/>
      <ellipse cx="48" cy="60" rx="6" ry="3.8" fill="url(#gCheek)"/>
      <ellipse cx="72" cy="60" rx="6" ry="3.8" fill="url(#gCheek)"/>
      <ellipse class="c-nose" cx="60" cy="57" rx="3.4" ry="2.6" fill="#eda763"/>
      <ellipse cx="59" cy="55.6" rx="1.1" ry=".8" fill="#ffd9ae" opacity=".9"/>
      <g class="c-eye-l" style="transform-origin:48px 47px">
        <ellipse cx="48" cy="47" rx="5.6" ry="6.2" fill="url(#gEye)"/>
        <circle cx="49" cy="48" r="2.9" fill="#5a3a20"/><circle cx="49.4" cy="48.4" r="1.5" fill="#1c1c1c"/>
        <circle cx="50.4" cy="45.8" r="1" fill="#fff"/><circle cx="47.8" cy="49.6" r=".55" fill="#fff" opacity=".8"/>
        <path class="c-lid-l" d="M42.4 47 a5.6 6.2 0 0 1 11.2 0" fill="#f0a95f" opacity="0"/>
      </g>
      <g class="c-eye-r" style="transform-origin:72px 47px">
        <ellipse cx="72" cy="47" rx="5.6" ry="6.2" fill="url(#gEye)"/>
        <circle cx="73" cy="48" r="2.9" fill="#5a3a20"/><circle cx="73.4" cy="48.4" r="1.5" fill="#1c1c1c"/>
        <circle cx="74.4" cy="45.8" r="1" fill="#fff"/><circle cx="71.8" cy="49.6" r=".55" fill="#fff" opacity=".8"/>
        <path class="c-lid-r" d="M66.4 47 a5.6 6.2 0 0 1 11.2 0" fill="#f0a95f" opacity="0"/>
      </g>
      <g class="c-brows">
        <path class="c-brow-l" d="M41 39.5 q6 -3.5 10.5 -1" stroke="#7c4a1e" stroke-width="2.6" fill="none" stroke-linecap="round"/>
        <path class="c-brow-r" d="M68.5 38.5 q6 -2.5 10.5 1" stroke="#7c4a1e" stroke-width="2.6" fill="none" stroke-linecap="round"/>
      </g>
      <g class="c-mouths">
        <path class="c-mouth c-m-smile" d="M50 68 q10 8 20 0" stroke="#8d4c1d" stroke-width="2.8" fill="none" stroke-linecap="round"/>
        <path class="c-mouth c-m-o" d="M55 68 a5 4.6 0 1 0 10 0 a5 4.6 0 1 0 -10 0" fill="#7a3a18" opacity="0"/>
        <path class="c-mouth c-m-grin" d="M49 67 q11 11 22 0 q-11 3 -22 0z" fill="#7a3a18" opacity="0"/>
        <path class="c-mouth c-m-smirk" d="M51 69 q9 4 17 -2" stroke="#8d4c1d" stroke-width="2.8" fill="none" stroke-linecap="round" opacity="0"/>
        <path class="c-mouth c-m-sleep" d="M54 69 q6 3 12 0" stroke="#8d4c1d" stroke-width="2.4" fill="none" stroke-linecap="round" opacity="0"/>
      </g>
      <g class="c-hat" style="transform-origin:60px 32px">
        <ellipse cx="60" cy="33" rx="32" ry="8.6" fill="url(#gHat)"/>
        <ellipse cx="60" cy="33" rx="32" ry="8.6" fill="url(#pWeave)" opacity=".25"/>
        <path d="M40 33 a20 13 0 0 1 40 0 z" fill="url(#gHat)"/>
        <path d="M40 33 a20 13 0 0 0 40 0" fill="none" stroke="#b98f2e" stroke-width="1.2" opacity=".6"/>
        <rect x="40" y="29" width="40" height="4.4" rx="2.2" fill="#a83232"/>
        <path d="M30 33.6 q30 5 60 0" stroke="rgba(0,0,0,.14)" stroke-width="2" fill="none" filter="url(#fSoft)"/>
      </g>
    </g>
    <g class="c-basket" style="transform-origin:20px 108px">
      <path d="M6 100 h30 l-5 19 h-20 z" fill="url(#gBasket)"/>
      <path d="M6 100 h30 M9.5 106 h23 M11.5 112 h19" stroke="#6f451f" stroke-width="1.6" fill="none" opacity=".7"/>
      <path d="M12 100 q9 -11 20 0" stroke="#6f451f" stroke-width="2.4" fill="none"/>
      <circle cx="13" cy="98" r="5" fill="url(#gTom)"/><circle cx="22" cy="95.5" r="5" fill="url(#gTom)"/><circle cx="30" cy="98" r="5" fill="url(#gTom)"/>
      <path d="M22 90 l-2 -2.6 M22 90 l2 -2.6" stroke="#2e9e57" stroke-width="1.4" stroke-linecap="round"/>
      <path d="M6 100 h30" stroke="rgba(255,255,255,.25)" stroke-width="1.4"/>
    </g>
  </g>
  <text class="c-zzz" x="88" y="18" font-size="16" fill="#999" display="none">z z z</text>
  <text class="c-bang" x="92" y="22" font-size="21" font-weight="900" fill="#d63031" display="none">!</text>
</svg>`;

export const TOMATO_SVG = (size = 28) => `
<svg width="${size}" height="${size}" viewBox="0 0 30 30" xmlns="http://www.w3.org/2000/svg">
  <defs><radialGradient id="gt${size}" cx="35%" cy="28%" r="78%">
    <stop offset="0%" stop-color="#ff7a68"/><stop offset="55%" stop-color="#d63031"/><stop offset="100%" stop-color="#a02222"/>
  </radialGradient></defs>
  <circle cx="15" cy="16.5" r="11.5" fill="url(#gt${size})"/>
  <ellipse cx="11.5" cy="12.5" rx="3.6" ry="2.6" fill="#ff9d8f" opacity=".75"/>
  <path d="M15 5 l-3 -4 M15 5 l3 -4 M15 5 l-5.4 -1 M15 5 l5.4 -1 M15 5 v-4.6" stroke="#2e9e57" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>`;

export function splatSvg(seed: number): string {
  const rnd = mulberry(seed);
  const pts: string[] = [];
  const n = 9 + Math.floor(rnd() * 4);
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const r = 17 + rnd() * 13;
    pts.push(`${i === 0 ? "M" : "L"}${(32 + Math.cos(a) * r).toFixed(1)} ${(32 + Math.sin(a) * r).toFixed(1)}`);
  }
  const seeds = Array.from({ length: 4 }, () =>
    `<ellipse cx="${24 + rnd() * 16}" cy="${24 + rnd() * 16}" rx="1.6" ry="2.2" fill="#f5d3a0" transform="rotate(${Math.floor(rnd() * 360)} ${24 + rnd() * 16} ${24 + rnd() * 16})"/>`).join("");
  const drips = `<path d="M${28 + rnd() * 8} 40 q1 7 0 9" stroke="#b02222" stroke-width="2.4" stroke-linecap="round" fill="none"/>`;
  return `<svg width="70" height="70" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
    <defs><radialGradient id="gs${seed % 999}" cx="42%" cy="38%" r="70%">
      <stop offset="0%" stop-color="#e74c3c"/><stop offset="100%" stop-color="#a02020"/></radialGradient></defs>
    <path d="${pts.join(" ")} Z" fill="url(#gs${seed % 999})" opacity=".95"/>
    ${seeds}${drips}
    <ellipse cx="${26 + rnd() * 6}" cy="${26 + rnd() * 6}" rx="4" ry="3" fill="#ff8a7a" opacity=".5"/>
  </svg>`;
}

function mulberry(a: number) {
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
