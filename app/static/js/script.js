document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("darkModeToggle");
    const body = document.body;
    const nav = document.querySelector("nav");

    // Load mode from localStorage
    const isDark = localStorage.getItem("darkMode") === "true";
    if (isDark) {
        body.classList.add("dark-mode");
        nav.classList.add("dark-mode");
    }

    // Toggle handler
    toggle.addEventListener("click", () => {
        body.classList.toggle("dark-mode");
        nav.classList.toggle("dark-mode");
        localStorage.setItem("darkMode", body.classList.contains("dark-mode"));
    });

    // Example: Show/hide sections dynamically
    const toggles = document.querySelectorAll("[data-toggle-target]");
    toggles.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-toggle-target");
            const target = document.getElementById(targetId);
            if (target) {
                target.classList.toggle("hidden");
            }
        });
    });
});
