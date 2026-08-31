const form = document.getElementById("fixtureForm");

// arrow function 
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

// closure to keep track of how many times the form was submitted
const submissionCounter = (() => {
  let count = 0;
  return () => {
    count++;
    return count;
  };
})();

form.addEventListener("submit", (e) => {
  e.preventDefault();

  if (!validateForm()) return;

  const fixture = {
    fixtureTitle: document.getElementById("fixtureTitle").value,
    venue: document.getElementById("venue").value,
    email: document.getElementById("email").value,
    details: document.getElementById("details").value,
    status: document.getElementById("status").value,
    termsAccepted: document.getElementById("terms").checked
  };
  const jsonString = JSON.stringify(fixture);
  console.log("Form data as JSON:", jsonString);
  const parsed = JSON.parse(jsonString);
  const { fixtureTitle, email } = parsed;
  console.log("Fixture Title:", fixtureTitle);
  console.log("Email:", email);
  const updated = { ...parsed, submissionDate: new Date().toISOString() };
  console.log("Updated with date:", updated);
  const count = submissionCounter();
  console.log("Submission count:", count);
  form.reset();
  alert("Fixture submitted! Check the console.");
});