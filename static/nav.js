const NAV_ITEMS = [
  { key: "home", href: "/", label: "ホーム", img: "images/nav/home.png" },
  { key: "recipe", href: "/recipe", label: "レシピ", img: "images/nav/recipe.png" },
  { key: "logs", href: "/record", label: "食事", img: "images/nav/meal.png" },
  { key: "goal", href: "/goals", label: "目標", img: "images/nav/goal.png" },
  { key: "radio", href: "/radio", label: "ラジオ", img: "images/nav/radio.png" },
  { key: "profile", href: "/profile", label: "設定", img: "images/nav/settings.png" },
];

function renderNav(activeKey) {
  const el = document.getElementById("nav");
  if (!el) return;
  el.innerHTML = NAV_ITEMS.map(it => `
    <a class="navitem ${it.key === activeKey ? "active" : ""}" href="${it.href}">
      <img src="${it.img}" alt="${it.label}" width="26" height="26" style="border-radius:8px;object-fit:cover;">
      ${it.label}
    </a>
  `).join("");
}

async function logout() {
  await fetch("/logout", { method: "POST" });
  window.location.href = "/login";
}
