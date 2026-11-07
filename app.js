// Grab the page elements we need to read from or write to
const button = document.getElementById("go");
const output = document.getElementById("out");
const symptoms = document.getElementById("sym");
const fileInput = document.getElementById("file");
const consent = document.getElementById("ok");

// Show a message in the answer box
function show(message) {
  output.style.display = "block";
  output.textContent = message;
}

// Shrink a photo and turn it into text (base64) so it can be sent to the server
function photoToBase64(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.85).split(",")[1]);
    };
    img.onerror = reject;
    img.src = url;
  });
}

// Runs when the visitor clicks Analyze
button.addEventListener("click", async () => {
  const text = symptoms.value.trim();
  const file = fileInput.files[0];

  // 1. Check the input before doing anything
  if (!text && !file) return show("Add your symptoms or a report first.");
  if (!consent.checked) return show("Please tick the box to confirm you understand this is general information.");

  button.disabled = true;
  button.textContent = "Analyzing…";
  show("Reading what you shared…");

  try {
    // 2. Package everything the server needs
    const data = { text, reportText: "", image: "" };

    if (file) {
      if (file.type.startsWith("image/")) {
        data.image = await photoToBase64(file);
      } else if (file.type.startsWith("text/") || /\.(txt|csv)$/i.test(file.name)) {
        data.reportText = (await file.text()).slice(0, 20000);
      } else {
        return show("That file type isn’t supported. Upload a photo or text file, or paste the text above.");
      }
    }

    // 3. Send it to our server function and wait for the reply
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const result = await response.json();

    // 4. Show the answer, or the error message
    show(response.ok ? result.text : result.error || "Something went wrong. Try again.");
  } catch (error) {
    show("Something went wrong. Check your connection and try again.");
  } finally {
    button.disabled = false;
    button.textContent = "Analyze";
  }
});
