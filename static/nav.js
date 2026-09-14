const NAV_ITEMS = [
  { key: "home", href: "/", label: "ホーム", icon: '<path d="M3 10l7-6 7 6"/><path d="M5 9v7a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V9"/>' },
  { key: "recipe", href: "/recipe", label: "レシピ", icon: '<path d="M3 9h14a7 7 0 0 1-14 0Z"/><path d="M6 9c0-2 .5-3.5 1.5-4.5M13.5 4.5C14.5 5.5 15 7 15 9"/>' },
  { key: "logs", href: "/record", label: "食事", icon: '<rect x="4" y="3.5" width="12" height="14" rx="1.8"/><path d="M7.5 3.5V3a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 12.5 3v.5"/><path d="M7 10.5l2 2 4-4.5"/>' },
  { key: "weight", href: "/weight-log", label: "体重", icon: '<path d="M3 13l4-3 3 2 6-7"/><circle cx="16" cy="5" r="1.4" fill="currentColor" stroke="none"/>' },
  { key: "goal", href: "/goals", label: "目標", icon: '<circle cx="10" cy="10" r="7"/><circle cx="10" cy="10" r="3.6"/><circle cx="10" cy="10" r="0.6" fill="currentColor" stroke="none"/>' },
  { key: "radio", href: "/radio", label: "ラジオ", icon: '<circle cx="10" cy="12" r="5"/><path d="M10 9v3l2 1"/><path d="M6 6L4 4M14 6l2-2"/>' },
  { key: "discover", href: "/discover", label: "みんな", icon: '<path d="M3 10a7 7 0 0 1 14 0"/><path d="M3 10a7 7 0 0 0 14 0" opacity="0.4"/><circle cx="10" cy="10" r="1.4" fill="currentColor" stroke="none"/>' },
  { key: "profile", href: "/profile", label: "設定", icon: '<circle cx="10" cy="7" r="3"/><path d="M4 17c0-3.3 2.7-6 6-6s6 2.7 6 6"/>' },
];

function renderNav(activeKey) {
  const el = document.getElementById("nav");
  if (!el) return;
  el.innerHTML = NAV_ITEMS.map(it => `
    <a class="navitem ${it.key === activeKey ? "active" : ""}" href="${it.href}">
      <svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${it.icon}</svg>
      ${it.label}
    </a>
  `).join("");
}

async function logout() {
  await fetch("/logout", { method: "POST" });
  window.location.href = "/login";
}
