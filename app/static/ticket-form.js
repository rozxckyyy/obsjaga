const specialty = document.getElementById("specialty");
const preset = document.getElementById("preset");
const description = document.getElementById("description");
const choices = document.getElementById("preset-options").content.querySelectorAll("option");

function updatePresets() {
  const matches = Array.from(choices).filter((choice) => choice.dataset.specialty === specialty.value);
  let prompt = "Сначала выберите специальность";
  if (specialty.value) {
    prompt = matches.length ? "Выберите пресет" : "Нет доступных пресетов";
  }
  preset.replaceChildren(new Option(prompt, ""), ...matches.map((choice) => choice.cloneNode(true)));
  preset.disabled = matches.length === 0;
}

specialty.addEventListener("change", updatePresets);
preset.addEventListener("change", () => {
  const selected = preset.selectedOptions[0];
  if (selected?.value) {
    description.value = selected.dataset.description;
  }
});
updatePresets();
