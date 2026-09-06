const form = document.getElementById("shorten-form");
const originalUrlInput = document.getElementById("original-url");
const result = document.getElementById("result");

form.addEventListener("submit", async function (event) {
    event.preventDefault();

    const originalUrl = originalUrlInput.value;

    const response = await fetch("/shorten", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            original_url: originalUrl
        })
    });

    const data = await response.json();

    if (response.ok) {
        result.innerHTML = `
            <p>Your shortened URL:</p>
            <a href="/${data.short_url}" target="_blank">
                ${window.location.origin}/${data.short_url}
            </a>
        `;
    } else {
        result.textContent = data.error;
    }
});