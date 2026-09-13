const NAV_ITEMS = [
  { key: "recipe", href: "/", label: "レシピ提案", icon: '<path d="M3 9h14a7 7 0 0 1-14 0Z"/><path d="M6 9c0-2 .5-3.5 1.5-4.5M13.5 4.5C14.5 5.5 15 7 15 9"/>' },
  { key: "logs", href: "/record", label: "食事ログ", icon: '<rect x="4" y="3.5" width="12" height="14" rx="1.8"/><path d="M7.5 3.5V3a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 12.5 3v.5"/><path d="M7 10.5l2 2 4-4.5"/>' },
  { key: "goal", href: "/goals", label: "目標", icon: '<circle cx="10" cy="10" r="7"/><circle cx="10" cy="10" r="3.6"/><circle cx="10" cy="10" r="0.6" fill="currentColor" stroke="none"/>' },
  { key: "weight", href: "/weight-log", label: "体重記録", icon: '<path d="M3 13l4-3 3 2 6-7"/><circle cx="16" cy="5" r="1.4" fill="currentColor" stroke="none"/>' },
  { key: "radio", href: "/radio", label: "ラジオ", icon: '<circle cx="10" cy="12" r="5"/><path d="M10 9v3l2 1"/><path d="M6 6L4 4M14 6l2-2"/>' },
];

function renderNav(activeKey) {
  const el = document.getElementById("nav");
  if (!el) return;
  el.innerHTML = NAV_ITEMS.map(it => `
    <a class="navitem ${it.key}${it.key === activeKey ? " active" : ""}" href="${it.href}">
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${it.icon}</svg>
      ${it.label}
    </a>
  `).join("") + `
    <a class="navitem" href="/profile" style="margin-left:auto;">設定</a>
    <a class="navitem" href="#" id="logout-link">
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 4H4.5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1H8"/><path d="M12 14l4-4-4-4"/><path d="M16 10H7.5"/></svg>
      ログアウト
    </a>
  `;
  document.getElementById("logout-link").addEventListener("click", async (e) => {
    e.preventDefault();
    await fetch("/logout", { method: "POST" });
    window.location.href = "/login";
  });
}
