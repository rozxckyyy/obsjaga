for (const button of document.querySelectorAll(".mobile-disclosure")) {
  const panel = document.getElementById(button.getAttribute("aria-controls"));
  button.hidden = false;
  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
  });

  const closeOnEscape = (event) => {
    if (event.key !== "Escape" || !button.getClientRects().length) return;
    if (button.getAttribute("aria-expanded") === "true") {
      button.setAttribute("aria-expanded", "false");
      button.focus();
    }
  };
  button.addEventListener("keydown", closeOnEscape);
  panel.addEventListener("keydown", closeOnEscape);
}
