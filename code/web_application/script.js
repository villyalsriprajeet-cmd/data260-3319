/* Community Sports League Fixtures */
const form = document.getElementById("fixtureForm");

// state elements
const els = {
  loading: document.getElementById("stateLoading"),
  error: document.getElementById("stateError"),
  errorText: document.getElementById("errorText"),
  empty: document.getElementById("stateEmpty"),
  list: document.getElementById("fixtureList"),
  searchBox: document.getElementById("searchBox"),
  searchBtn: document.getElementById("searchBtn"),
  clearBtn: document.getElementById("clearBtn"),
  retryBtn: document.getElementById("retryBtn"),
};

let fixtures = [
  { id: 1, fixtureTitle: "Spartans vs Bulldogs - Matchweek 5",
    venue: "Spartan Soccer Complex", status: "Scheduled" },
];
let nextId = 2;

// form validation 
const validateForm = () => {
  const details = document.getElementById("details").value;
  const terms = document.getElementById("terms").checked;
  if (details.length <= 25) {
    alert("Match details must be more than 25 characters.");
    return false;
  }
  if (!terms) {
    alert("Please agree to the terms and conditions.");
    return false;
  }
  return true;
};

const submissionCounter = (() => {
  let count = 0;
  return () => { count++; return count; };
})();

// visible loading, empty, and error states.
function showOnly(state) {
  els.loading.hidden = state !== "loading";
  els.error.hidden = state !== "error";
  els.empty.hidden = state !== "empty";
  els.list.hidden = state !== "data";
}
function renderList(items) {
  els.list.innerHTML = "";
  items.forEach((f) => {
    const li = document.createElement("li");
    li.className = "fixture-item";
    const h3 = document.createElement("h3");
    h3.textContent = f.fixtureTitle;
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = f.venue;
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = f.status || "Scheduled";
    li.append(h3, meta, badge);
    els.list.appendChild(li);
  });
}
function loadFixtures(opts = {}) {
  const query = (els.searchBox.value || "").trim().toLowerCase();
  showOnly("loading");
  setTimeout(() => {
    try {
      if (opts.fail) throw new Error("Could not reach the fixtures service.");
      let items = fixtures;
      if (query) {
        items = fixtures.filter(
          (f) =>
            f.fixtureTitle.toLowerCase().includes(query) ||
            f.venue.toLowerCase().includes(query)
        );
      }
      if (items.length === 0) {
        els.empty.querySelector("p").textContent = query
          ? `No fixtures match "${els.searchBox.value}".`
          : "No fixtures yet. Add your first fixture using the form above.";
        showOnly("empty");
      } else {
        renderList(items);
        showOnly("data");
      }
    } catch (err) {
      els.errorText.textContent = err.message;
      showOnly("error");
    }
  }, 400);
}

// events
form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (!validateForm()) return;
  const fixture = {
    id: nextId++,
    fixtureTitle: document.getElementById("fixtureTitle").value,
    venue: document.getElementById("venue").value,
    email: document.getElementById("email").value,
    details: document.getElementById("details").value,
    status: document.getElementById("status").value,
    termsAccepted: document.getElementById("terms").checked,
  };
  const jsonString = JSON.stringify(fixture);
  const parsed = JSON.parse(jsonString);
  const updated = { ...parsed, submissionDate: new Date().toISOString() };
  console.log("Submission count:", submissionCounter());
  fixtures.push(updated);
  form.reset();
  els.searchBox.value = "";
  loadFixtures();
});
els.searchBtn.addEventListener("click", () => loadFixtures());
els.searchBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadFixtures();
});
els.clearBtn.addEventListener("click", () => {
  els.searchBox.value = "";
  loadFixtures();
});
els.retryBtn.addEventListener("click", () => loadFixtures());
loadFixtures();