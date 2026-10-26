// One set of line icons, drawn like the ones at the top (a 24 grid, no fill, round ends), in place of the
// colour emoji the pages used as icons: 97 different ones in 455 places, which made the Workshop look like a
// web page rather than one tool ("looking generic, hard to follow, or garish", the user, 2026-10-26). The pages
// keep writing their emoji; each one is swapped for its icon as it's drawn, so every page, window, menu and
// message gets them, and the icon takes the colour of the text it sits in, in every theme. In a list box
// (an <option>) and in tooltips, where a drawing can't go, the emoji is left out.
const ICONS = {
  dice: '<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="8.5" cy="8.5" r=".9"/><circle cx="15.5" cy="15.5" r=".9"/><circle cx="12" cy="12" r=".9"/><circle cx="15.5" cy="8.5" r=".9"/><circle cx="8.5" cy="15.5" r=".9"/>',
  chat: '<path d="M4 5.5h16v10H10l-4.5 3.5v-3.5H4z"/>',
  person: '<circle cx="12" cy="8" r="3.6"/><path d="M4.8 20c.9-4 3.7-6 7.2-6s6.3 2 7.2 6"/>',
  people: '<circle cx="9" cy="8.5" r="3.2"/><path d="M3 19.5c.7-3.4 3-5.2 6-5.2s5.3 1.8 6 5.2"/><path d="M15.5 5.6a3 3 0 0 1 0 5.8M17.6 14.6c1.8.6 3 2.2 3.4 4.9"/>',
  palette: '<path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.3 0 1.9-.8 1.9-1.8 0-1.4-1.3-1.7-1.3-3 0-1 .8-1.7 1.9-1.7h2.3a3.7 3.7 0 0 0 3.7-3.7C20.5 6.5 16.7 3.5 12 3.5z"/><circle cx="7.6" cy="11" r="1"/><circle cx="10" cy="7.3" r="1"/><circle cx="14.4" cy="7.3" r="1"/>',
  brush: '<path d="M14.5 4.5 19.5 9.5 11 18l-5-5z"/><path d="M6 13c-1.8.4-2.6 1.8-2.5 3.6 0 1.4-.7 2.4-1 2.9 2.7.4 5.6-.6 6.5-3.5"/>',
  pin: '<path d="M12 21s-6.5-6.2-6.5-11.3a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21z"/><circle cx="12" cy="9.7" r="2.4"/>',
  scroll: '<path d="M7 4h11a2 2 0 0 1 2 2v1h-3"/><path d="M17 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-1h11"/><path d="M7 4a2 2 0 0 0-2 2v11M8.5 9h5M8.5 12.5h5"/>',
  page: '<path d="M6 3.5h8l4 4v13H6z"/><path d="M14 3.5v4h4M9 12h6M9 15.5h6"/>',
  warn: '<path d="M12 4 21 19.5H3z"/><path d="M12 10v4.2M12 17.2v.1"/>',
  sound: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6M18 6.5a7.8 7.8 0 0 1 0 11"/>',
  box: '<path d="M12 3.5 20 7.5v9L12 20.5 4 16.5v-9z"/><path d="M4 7.5 12 11.5 20 7.5M12 11.5v9"/>',
  save: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
  wand: '<path d="M4 20 14.5 9.5"/><path d="m13 8 3 3"/><path d="M17.5 3.5v3M16 5h3M20 9.5v2.4M18.8 10.7h2.4M10 3.8v2M9 4.8h2"/>',
  sparkle: '<path d="M12 3.5c.6 4 1.9 5.9 6 6.5-4.1.6-5.4 2.5-6 6.5-.6-4-1.9-5.9-6-6.5 4.1-.6 5.4-2.5 6-6.5z"/><path d="M18.5 15.5c.3 1.6.8 2.2 2.2 2.5-1.4.3-1.9.9-2.2 2.5-.3-1.6-.8-2.2-2.2-2.5 1.4-.3 1.9-.9 2.2-2.5z"/>',
  swirl: '<path d="M12 12a2 2 0 1 1 2 2c-2.4 0-4-1.9-4-4a4 4 0 0 1 4-4c3.3 0 6 2.6 6 6a8 8 0 0 1-8 8 8 8 0 0 1-8-8"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
  door: '<path d="M6 20.5V4.5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v16M4 20.5h16"/><path d="M14.5 12.5v.1"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.3M12 18.2v2.3M3.5 12h2.3M18.2 12h2.3M6 6l1.6 1.6M16.4 16.4 18 18M6 18l1.6-1.6M16.4 7.6 18 6"/><circle cx="12" cy="12" r="6.2"/>',
  paw: '<ellipse cx="12" cy="15.8" rx="3.8" ry="3.2"/><circle cx="6.6" cy="10.6" r="1.6"/><circle cx="9.6" cy="6.8" r="1.6"/><circle cx="14.4" cy="6.8" r="1.6"/><circle cx="17.4" cy="10.6" r="1.6"/>',
  wrench: '<path d="M14.5 4.2a4.6 4.6 0 0 0 5.3 5.3l-9.3 9.3a2.4 2.4 0 0 1-3.4-3.4l9.3-9.3a4.6 4.6 0 0 0-1.9-1.9z"/><path d="m15.5 5 1.7 1.8"/>',
  hammer: '<path d="m13 7 4 4"/><path d="M4.5 19.5 13.5 10.5"/><path d="M11.5 5.5 15 2l7 7-3.5 3.5z"/><path d="M3 21h8"/>',
  pulse: '<path d="M3 12.5h4l2-5 3.5 10 2.3-6.5 1.4 1.5H21"/>',
  puzzle: '<path d="M5 8h3a2 2 0 1 1 4 0h3v3a2 2 0 1 1 0 4v4H5v-4a2 2 0 1 0 0-4z"/>',
  brick: '<path d="M3.5 6h17v12h-17z"/><path d="M3.5 10h17M3.5 14h17M9 6v4M15 6v4M6.5 10v4M12 10v4M17.5 10v4M9 14v4M15 14v4"/>',
  folder: '<path d="M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4.5l2 2.5H19a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 17.5z"/>',
  settle: '<path d="M12 3.5v10M8 9.5l4 4 4-4M4 19.5h16"/>',
  chair: '<path d="M7 3.5v17M7 12h10v8.5M17 12V7M7 7h10"/>',
  house: '<path d="M4 11 12 4.5 20 11"/><path d="M6 9.5v10h12v-10M10 19.5v-5h4v5"/>',
  temple: '<path d="M3.5 9 12 4l8.5 5zM5 20h14M4 9.5h16M6.5 10v8M10 10v8M14 10v8M17.5 10v8"/>',
  search: '<circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5 5"/>',
  wave: '<path d="M7.5 12V6.5a1.3 1.3 0 0 1 2.6 0V11M10.1 10V5a1.3 1.3 0 0 1 2.6 0v5M12.7 10V6a1.3 1.3 0 0 1 2.6 0v5.5M15.3 11V8.5a1.3 1.3 0 0 1 2.6 0V14a6 6 0 0 1-6 6h-.6a6 6 0 0 1-4.8-2.4L4 14.5a1.4 1.4 0 0 1 2.2-1.7L7.5 14"/>',
  film: '<rect x="4" y="3.5" width="16" height="17" rx="1.5"/><path d="M8 3.5v17M16 3.5v17M4 8h4M4 12h4M4 16h4M16 8h4M16 12h4M16 16h4"/>',
  bulb: '<path d="M9 17h6M10 20.5h4"/><path d="M8.5 14.5A5.8 5.8 0 0 1 6.2 10a5.8 5.8 0 0 1 11.6 0 5.8 5.8 0 0 1-2.3 4.5c-.5.4-.5 1-.5 1.5V17H9v-1c0-.5 0-1.1-.5-1.5z"/>',
  compass: '<circle cx="12" cy="12" r="8.5"/><path d="m15.5 8.5-2.1 4.9-4.9 2.1 2.1-4.9z"/>',
  map: '<path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20z"/><path d="M9 4v13.5M15 6.5V20"/>',
  play: '<rect x="3" y="7.5" width="18" height="10" rx="4"/><path d="M7.5 11v3M6 12.5h3M15.5 11.5v.1M17.5 13.5v.1"/>',
  link: '<path d="M10 14a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1 1"/><path d="M14 10a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1-1"/>',
  lock: '<rect x="5" y="10.5" width="14" height="10" rx="1.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3M12 14.5v2"/>',
  unlock: '<rect x="5" y="10.5" width="14" height="10" rx="1.5"/><path d="M8 10.5V7.5a4 4 0 0 1 7.6-1.7M12 14.5v2"/>',
  leaf: '<path d="M5 19c0-8 5.5-13.5 14.5-14.5C19 13.5 13.5 19 5 19z"/><path d="M5 19c3-4.5 6-7 10-9.5"/>',
  books: '<path d="M5 4.5h3v15H5zM8 4.5h3v15H8z"/><path d="m12.5 6 2.9-.8 3.9 14.5-2.9.8z"/>',
  sword: '<path d="M14.5 4.5h5v5L10 19l-5-5z"/><path d="m6.5 12.5-2 2 5 5 2-2M5 19l-1.5 1.5"/>',
  shield: '<path d="M12 3.5 19 6v5.5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/>',
  picture: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="9.5" r="1.6"/><path d="m3.5 17 5-5 4 4 2.5-2.5 5.5 5"/>',
  broom: '<path d="M19.5 4.5 12 12"/><path d="M9.5 10.5 13.5 14.5 11 20.5c-3-.5-6-3-6.5-6.5z"/><path d="M7.3 15.5 9 17.2"/>',
  flask: '<path d="M9.5 3.5h5M10.5 3.5v5.5L5.2 18a1.8 1.8 0 0 0 1.6 2.5h10.4a1.8 1.8 0 0 0 1.6-2.5L13.5 9V3.5"/><path d="M7.5 14.5h9"/>',
  moon: '<path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z"/>',
  cap: '<path d="M2.5 9.5 12 5l9.5 4.5L12 14z"/><path d="M6.5 11.5v4.5c3 2 8 2 11 0v-4.5M21.5 9.5v5"/>',
  mask: '<path d="M4 5.5c5 1.5 11 1.5 16 0v6a8 8 0 0 1-16 0z"/><path d="M8 10.5h2M14 10.5h2M9 15c1.8 1.3 4.2 1.3 6 0"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.4 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.4-3.5-8.5s1.1-6.1 3.5-8.5z"/>',
  bag: '<path d="M6 8.5h12l-1 12H7z"/><path d="M9 10.5V7a3 3 0 0 1 6 0v3.5"/>',
  key: '<circle cx="8" cy="15.5" r="4"/><path d="m11 12.5 8.5-8.5M16.5 7l2.5 2.5M14 9.5l2 2"/>',
  magnet: '<path d="M6 4.5v7a6 6 0 0 0 12 0v-7h-4v7a2 2 0 0 1-4 0v-7z"/><path d="M6 8.5h4M14 8.5h4"/>',
  pencil: '<path d="M15.5 4.5l4 4L8 20H4v-4z"/><path d="m13.5 6.5 4 4"/>',
  sunrise: '<path d="M3.5 18.5h17M6.5 18.5a5.5 5.5 0 0 1 11 0M12 4.5v3.5M4.6 11.1l2 1.2M19.4 11.1l-2 1.2M9.5 6.5 12 4l2.5 2.5"/>',
  bone: '<path d="M8 15.5 15.5 8M8 15.5a2.4 2.4 0 1 1-3.3 3.3 2.4 2.4 0 1 1-1.2-3.4 2.4 2.4 0 1 1 3.4-1.2zM15.5 8a2.4 2.4 0 1 1 3.3-3.3 2.4 2.4 0 1 1 1.2 3.4 2.4 2.4 0 1 1-3.4 1.2"/>',
  bubbles: '<circle cx="9" cy="14" r="4.5"/><circle cx="16.5" cy="7.5" r="3"/><circle cx="17" cy="16.5" r="1.8"/>',
  sign: '<path d="M12 3.5v17M8.5 20.5h7"/><path d="M5 6.5h12l2.5 2.5L17 11.5H5z"/>',
  window: '<rect x="4.5" y="3.5" width="15" height="17" rx="1"/><path d="M12 3.5v17M4.5 12h15"/>',
  scissors: '<circle cx="6.5" cy="7" r="2.8"/><circle cx="6.5" cy="17" r="2.8"/><path d="M8.7 8.8 20 17M8.7 15.2 20 7"/>',
  chart: '<path d="M4 20.5h16M6.5 20.5v-6M11 20.5v-11M15.5 20.5v-8M20 20.5V5"/>',
  coin: '<ellipse cx="12" cy="7" rx="7" ry="3"/><path d="M5 7v5c0 1.7 3.1 3 7 3s7-1.3 7-3V7M5 12v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5"/>',
  trash: '<path d="M4 6.5h16M9.5 6.5V4h5v2.5M6 6.5l1 14h10l1-14M10 10.5v6M14 10.5v6"/>',
  candle: '<path d="M9 9.5h6v11H9z"/><path d="M12 9.5V7.5M12 3.5c-1.3 1.4-1.5 2.4-.8 3 .5.5 1.2.5 1.6 0 .6-.6.4-1.6-.8-3z"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
  sun: '<circle cx="12" cy="12" r="3.8"/><path d="M12 2.8v2.2M12 19v2.2M2.8 12H5M19 12h2.2M5.5 5.5 7 7M17 17l1.5 1.5M5.5 18.5 7 17M17 7l1.5-1.5"/>',
  cloud: '<path d="M7 18.5h10.5a3.7 3.7 0 0 0 .5-7.4 6 6 0 0 0-11.6-.6A4 4 0 0 0 7 18.5z"/>',
  cloudsun: '<path d="M8 19h9.5a3.4 3.4 0 0 0 .4-6.8 5.4 5.4 0 0 0-10.4-.5A3.7 3.7 0 0 0 8 19z"/><path d="M5.5 3.5v1.6M2 7h1.6M3 4.5l1.1 1.1"/>',
  fog: '<path d="M4 8.5h16M3 12.5h13M6 16.5h15M5 20.5h10"/>',
  rain: '<path d="M7 14.5h10.5a3.5 3.5 0 0 0 .5-7 5.7 5.7 0 0 0-11-.6A3.8 3.8 0 0 0 7 14.5z"/><path d="m8.5 17.5-1 2.5M12.5 17.5l-1 2.5M16.5 17.5l-1 2.5"/>',
  storm: '<path d="M7 14h10.5a3.5 3.5 0 0 0 .5-7 5.7 5.7 0 0 0-11-.6A3.8 3.8 0 0 0 7 14z"/><path d="m12.5 14-2 3.5h3l-2 3.5"/>',
  ash: '<path d="M3.5 20.5 9 9.5h6l5.5 11z"/><path d="M10 9.5c-1-2.5.5-4.5 2-5 0 1.5 1.5 2 2.5 1.2.6 1.4 0 2.8-.5 3.8"/>',
  blight: '<circle cx="12" cy="12" r="2"/><path d="M12 10a6 6 0 0 1 0-6.5 6 6 0 0 1 0 6.5zM13.7 13a6 6 0 0 1 5.7 3.2 6 6 0 0 1-5.7-3.2zM10.3 13a6 6 0 0 1-5.7 3.2A6 6 0 0 1 10.3 13z"/>',
  snow: '<path d="M12 3.5v17M4.6 7.75l14.8 8.5M4.6 16.25l14.8-8.5M9.5 4.8 12 6.5l2.5-1.7M9.5 19.2 12 17.5l2.5 1.7"/>',
  egg: '<path d="M12 3.5c3.5 0 6.5 5.6 6.5 10a6.5 6.5 0 0 1-13 0c0-4.4 3-10 6.5-10z"/>',
  gift: '<path d="M4 9.5h16v4H4zM5.5 13.5h13v7h-13zM12 9.5v11"/><path d="M12 9.5c-1.5-3.5-5-4-5-1.8 0 1.8 3 1.8 5 1.8zM12 9.5c1.5-3.5 5-4 5-1.8 0 1.8-3 1.8-5 1.8z"/>',
  tree: '<path d="M12 21v-5M12 3.5 6 11.5h3L5 16h14l-4-4.5h3z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chest: '<path d="M4 10a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v9H4z"/><path d="M4 11.5h16M11 10h2v3h-2z"/>',
  star: '<path d="m12 4 2.4 5 5.4.7-4 3.7 1 5.4L12 16.2 7.2 18.8l1-5.4-4-3.7 5.4-.7z"/>',
  hand: '<path d="M7 11.5V7a1.3 1.3 0 0 1 2.6 0v3.5M9.6 10V5.5a1.3 1.3 0 0 1 2.6 0V10M12.2 10V6.5a1.3 1.3 0 0 1 2.6 0v4M14.8 10.5V9a1.3 1.3 0 0 1 2.6 0v5a6 6 0 0 1-6 6h-.5A5.4 5.4 0 0 1 5.5 15V13a1.5 1.5 0 0 1 3 0"/>',
};

// which icon each emoji the pages write becomes (the same thing, the same icon)
const EMO_ICON = {
  '🎲': 'dice', '💬': 'chat', '🗣': 'chat', '👋': 'wave', '👤': 'person', '🧍': 'person', '🚶': 'person', '🧝': 'mask', '🎭': 'mask',
  '👥': 'people', '🎨': 'palette', '🖌': 'brush', '📍': 'pin', '📌': 'pin', '📜': 'scroll', '📝': 'page', '🗒': 'page', '📄': 'page', '📋': 'page', '📘': 'books',
  '⚠': 'warn', '🔊': 'sound', '📦': 'box', '🧊': 'box', '🎁': 'gift', '💾': 'save', '🪄': 'wand', '✨': 'sparkle', '🌀': 'swirl', '👁': 'eye',
  '🚪': 'door', '⚙': 'gear', '🐾': 'paw', '🔧': 'wrench', '🧰': 'chest', '⚒': 'hammer', '🩺': 'pulse', '🧩': 'puzzle', '🧱': 'brick', '🏗': 'brick', '🏘': 'house',
  '📂': 'folder', '📁': 'folder', '🗂': 'folder', '🫳': 'settle', '🪑': 'chair', '🏠': 'house', '🏝': 'map', '🏛': 'temple', '🔎': 'search', '🔍': 'search',
  '🎞': 'film', '💡': 'bulb', '🧭': 'compass', '🗺': 'map', '🎮': 'play', '🔗': 'link', '🔒': 'lock', '🔐': 'lock', '🔓': 'unlock',
  '🌿': 'leaf', '🌾': 'leaf', '🌳': 'tree', '📚': 'books', '🗡': 'sword', '🛡': 'shield', '🖼': 'picture', '🧹': 'broom', '🧪': 'flask', '🌙': 'moon',
  '🎓': 'cap', '🌐': 'globe', '🎒': 'bag', '🗝': 'key', '🧲': 'magnet', '✏': 'pencil', '🌄': 'sunrise', '🦴': 'bone', '🫧': 'bubbles', '🪧': 'sign',
  '🪟': 'window', '✂': 'scissors', '📊': 'chart', '🪙': 'coin', '💰': 'coin', '🗑': 'trash', '🕯': 'candle', '🕘': 'clock',
  '☀': 'sun', '🌦': 'cloudsun', '⛅': 'cloudsun', '☁': 'cloud', '🌫': 'fog', '🌧': 'rain', '⛈': 'storm', '🌋': 'ash', '☣': 'blight', '🌨': 'snow', '❄': 'snow',
  '🥚': 'egg', '✋': 'hand', '🖐': 'hand', '➕': 'plus', '⭐': 'star',
};

// (the colour pictographs, and the few older signs browsers draw in colour too; not the plain marks the pages
// use as text, ✕ ✓ ✦ ▶ ↶ ▾, which take the text's colour already)
const EMO_RE = /(?:[\u{1F300}-\u{1FAFF}]|[☀☁☣⚒⚙⚠⛅⛈✂✋✏✨❄➕⭐])️?/gu;
const ICON_SVG = name => `<svg class="wi" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
// (in these an emoji is only taken out: a list box can't hold a drawing, and code there is code)
const ICON_SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'CODE', 'PRE', 'svg', 'SVG', 'CANVAS', 'TITLE']);

const emoIn = s => { EMO_RE.lastIndex = 0; const r = EMO_RE.test(s); EMO_RE.lastIndex = 0; return r; };
function iconsIn(root){
  if (!root) return;
  const hits = [];
  if (root.nodeType === 3){ if (emoIn(root.data)) hits.push(root); }
  else if (root.nodeType === 1 || root.nodeType === 11){
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) if (emoIn(n.data)) hits.push(n);
  }
  for (const n of hits){
    const p = n.parentNode; if (!p) continue;
    const tag = p.nodeName;
    if (tag === 'OPTION' || tag === 'TITLE'){ n.data = n.data.replace(EMO_RE, '').replace(/^\s+/, ''); continue; }
    if (ICON_SKIP.has(tag) || p.closest && p.closest('[data-noicons], [contenteditable]')) continue;
    // (each emoji its icon, or out if it has none; the rest of the words as they were)
    const frag = document.createDocumentFragment();
    let last = 0;
    n.data.replace(EMO_RE, (m, at) => {
      if (at > last) frag.appendChild(document.createTextNode(n.data.slice(last, at)));
      const name = EMO_ICON[m.replace('️', '')];
      if (name){ const t = document.createElement('template'); t.innerHTML = ICON_SVG(name); frag.appendChild(t.content.firstChild); }
      last = at + m.length;
      return m;
    });
    if (last < n.data.length) frag.appendChild(document.createTextNode(n.data.slice(last)));
    p.replaceChild(frag, n);
  }
}
// (and in tooltips and the box hints, as words only)
function iconsAttrs(root){
  if (!root || !root.querySelectorAll) return;
  for (const e of [root, ...root.querySelectorAll('[title], [placeholder]')]){
    for (const a of ['title', 'placeholder']){
      const v = e.getAttribute && e.getAttribute(a);
      if (v && emoIn(v)) e.setAttribute(a, v.replace(EMO_RE, '').replace(/^\s+/, ''));
    }
  }
}

(function(){
  const c = document.createElement('style');
  c.textContent = `.wi{width:1.15em;height:1.15em;vertical-align:-.2em;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;flex:none;display:inline-block}
    button .wi,.btn .wi{margin-right:.12em}
    /* (the big cards' icons in the accent, as the buttons at the top draw theirs) */
    .ccard .wi{color:var(--gold);stroke-width:1.5}
    .ccard .ic .wi{width:26px;height:26px}`;
  document.head.appendChild(c);
  const run = () => { iconsIn(document.body); iconsAttrs(document.body); };
  run();
  let pend = 0;
  const queue = [];
  new MutationObserver(ms => {
    for (const m of ms){
      if (m.type === 'characterData') queue.push(m.target);
      else if (m.type === 'attributes') queue.push(m.target);
      else for (const n of m.addedNodes) queue.push(n);
    }
    if (!pend) pend = requestAnimationFrame(() => {
      pend = 0;
      const q = queue.splice(0);
      for (const n of q){ if (!n.isConnected) continue; iconsIn(n); if (n.nodeType === 1) iconsAttrs(n); }
    });
  }).observe(document.body, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['title', 'placeholder']});
})();
