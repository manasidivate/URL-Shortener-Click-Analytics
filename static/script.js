const form = document.getElementById("shorten-form");
const originalUrlInput = document.getElementById("original-url");
const aliasInput = document.getElementById("alias");
const expiresAtInput = document.getElementById("expires-at");
const shortenButton = document.getElementById("shorten-button");
const shortenButtonText = document.getElementById("shorten-button-text");
const formMessage = document.getElementById("form-message");

const successPanel = document.getElementById("success-panel");
const shortUrlElement = document.getElementById("short-url");
const copyButton = document.getElementById("copy-button");
const openButton = document.getElementById("open-button");
const analyticsButton = document.getElementById("analytics-button");
const copyMessage = document.getElementById("copy-message");

const analyticsSection = document.getElementById("analytics-section");
const analyticsUrl = document.getElementById("analytics-url");
const analyticsMessage = document.getElementById("analytics-message");
const refreshButton = document.getElementById("refresh-button");

const totalClicksElement = document.getElementById("total-clicks");
const uniqueVisitorsElement = document.getElementById("unique-visitors");
const timelineElement = document.getElementById("timeline");
const countriesList = document.getElementById("countries-list");
const referrersList = document.getElementById("referrers-list");

let currentShortCode = null;
let copyMessageTimeout = null;


function setMessage(element, message, type = "") {
    element.textContent = message;
    element.className = "message";

    if (type) {
        element.classList.add(`message-${type}`);
    }
}


function setShorteningState(isLoading) {
    shortenButton.disabled = isLoading;
    shortenButtonText.textContent = isLoading
        ? "Shortening..."
        : "Shorten URL";
}


function setAnalyticsState(isLoading) {
    refreshButton.disabled = isLoading;
    analyticsButton.disabled = isLoading;

    refreshButton.textContent = isLoading
        ? "Refreshing..."
        : "Refresh";
}


function buildShortUrl(shortCode) {
    return `${window.location.origin}/${encodeURIComponent(shortCode)}`;
}


function showSuccess(shortCode) {
    const fullShortUrl = buildShortUrl(shortCode);

    shortUrlElement.textContent = fullShortUrl;
    shortUrlElement.href = fullShortUrl;
    openButton.href = fullShortUrl;

    successPanel.classList.remove("hidden");

    setMessage(formMessage, "Short URL created.", "success");
    setMessage(copyMessage, "");
}


function validateUrl(value) {
    if (!value) {
        return "Please enter a URL.";
    }

    try {
        const url = new URL(value);

        if (!["http:", "https:"].includes(url.protocol)) {
            return "Please enter a valid HTTP or HTTPS URL.";
        }

        return "";
    } catch {
        return "Please enter a valid URL.";
    }
}


function getExpiryIsoValue(value) {
    if (!value) {
        return null;
    }

    const localDate = new Date(value);

    if (Number.isNaN(localDate.getTime())) {
        return null;
    }

    return localDate.toISOString();
}


async function shortenUrl(event) {
    event.preventDefault();

    const originalUrl = originalUrlInput.value.trim();
    const alias = aliasInput.value.trim();
    const expiresAt = expiresAtInput.value;

    setMessage(formMessage, "");
    setMessage(copyMessage, "");

    const validationError = validateUrl(originalUrl);

    if (validationError) {
        setMessage(formMessage, validationError, "error");
        originalUrlInput.focus();
        return;
    }

    if (expiresAt) {
        const expiryIsoValue = getExpiryIsoValue(expiresAt);

        if (!expiryIsoValue) {
            setMessage(
                formMessage,
                "Please enter a valid expiry date and time.",
                "error"
            );
            expiresAtInput.focus();
            return;
        }
    }

    setShorteningState(true);

    try {
        const requestBody = {
            original_url: originalUrl
        };

        if (alias) {
            requestBody.alias = alias;
        }

        if (expiresAt) {
            requestBody.expires_at = getExpiryIsoValue(expiresAt);
        }

        const response = await fetch("/shorten", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(requestBody)
        });

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error("The server returned an invalid response.");
        }

        if (!response.ok) {
            setMessage(
                formMessage,
                data.error || "Unable to shorten the URL.",
                "error"
            );
            return;
        }

        if (!data.short_url) {
            setMessage(
                formMessage,
                "The server did not return a short URL.",
                "error"
            );
            return;
        }

        currentShortCode = data.short_url;

        showSuccess(currentShortCode);

        analyticsSection.classList.add("hidden");
    } catch (error) {
        if (error instanceof TypeError) {
            setMessage(
                formMessage,
                "Unable to connect to the server. Please try again.",
                "error"
            );
        } else {
            setMessage(
                formMessage,
                error.message || "Something went wrong. Please try again.",
                "error"
            );
        }
    } finally {
        setShorteningState(false);
    }
}


function renderMetrics(data) {
    totalClicksElement.textContent = Number.isFinite(data.total_clicks)
        ? data.total_clicks
        : 0;

    uniqueVisitorsElement.textContent =
        Number.isFinite(data.unique_visitors)
            ? data.unique_visitors
            : 0;
}


function formatDate(dateString) {
    const date = new Date(`${dateString}T00:00:00`);

    if (Number.isNaN(date.getTime())) {
        return dateString;
    }

    return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric"
    });
}


function renderTimeline(clicksOverTime) {
    timelineElement.innerHTML = "";

    if (!Array.isArray(clicksOverTime) || clicksOverTime.length === 0) {
        const emptyState = document.createElement("p");
        emptyState.className = "empty-state";
        emptyState.textContent = "No timeline data available.";

        timelineElement.appendChild(emptyState);
        return;
    }

    const maxClicks = Math.max(
        ...clicksOverTime.map(item => Number(item.clicks) || 0),
        1
    );

    clicksOverTime.forEach(item => {
        const clicks = Number(item.clicks) || 0;

        const day = document.createElement("div");
        day.className = "timeline-day";

        const count = document.createElement("span");
        count.className = "timeline-count";
        count.textContent = clicks;

        const barContainer = document.createElement("div");
        barContainer.className = "timeline-bar-container";

        const bar = document.createElement("div");
        bar.className = "timeline-bar";

        const height = clicks === 0
            ? 0
            : Math.max((clicks / maxClicks) * 100, 8);

        bar.style.height = `${height}%`;

        const date = document.createElement("span");
        date.className = "timeline-date";
        date.textContent = formatDate(item.date);

        barContainer.appendChild(bar);

        day.appendChild(count);
        day.appendChild(barContainer);
        day.appendChild(date);

        timelineElement.appendChild(day);
    });
}


function renderRanking(container, items, labelKey) {
    container.innerHTML = "";

    if (!Array.isArray(items) || items.length === 0) {
        const emptyState = document.createElement("p");
        emptyState.className = "empty-state";

        emptyState.textContent =
            labelKey === "country"
                ? "Country data is unavailable yet."
                : "Referrer data is unavailable yet.";

        container.appendChild(emptyState);
        return;
    }

    items.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = "ranking-row";

        const rank = document.createElement("span");
        rank.className = "ranking-number";
        rank.textContent = index + 1;

        const name = document.createElement("span");
        name.className = "ranking-name";
        name.textContent = item[labelKey] || "Unknown";

        const clicks = document.createElement("span");
        clicks.className = "ranking-clicks";
        clicks.textContent = item.clicks ?? 0;

        row.appendChild(rank);
        row.appendChild(name);
        row.appendChild(clicks);

        container.appendChild(row);
    });
}


function renderAnalytics(data) {
    renderMetrics(data);
    renderTimeline(data.clicks_over_time);
    renderRanking(countriesList, data.top_countries, "country");
    renderRanking(referrersList, data.top_referrers, "referrer");
}


async function loadAnalytics() {
    if (!currentShortCode) {
        return;
    }

    analyticsSection.classList.remove("hidden");
    analyticsUrl.textContent = buildShortUrl(currentShortCode);

    setMessage(analyticsMessage, "");
    setAnalyticsState(true);

    try {
        const response = await fetch(
            `/${encodeURIComponent(currentShortCode)}/analytics`
        );

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error("The server returned an invalid response.");
        }

        if (!response.ok) {
            if (response.status === 404) {
                throw new Error("This short URL could not be found.");
            }

            throw new Error(
                data.error || "Unable to load analytics."
            );
        }

        renderAnalytics(data);

        setMessage(
            analyticsMessage,
            "Analytics updated.",
            "success"
        );
    } catch (error) {
        if (error instanceof TypeError) {
            setMessage(
                analyticsMessage,
                "Unable to connect to the server. Please try again.",
                "error"
            );
        } else {
            setMessage(
                analyticsMessage,
                error.message || "Unable to load analytics.",
                "error"
            );
        }
    } finally {
        setAnalyticsState(false);
    }
}


async function copyShortUrl() {
    const url = shortUrlElement.textContent;

    if (!url) {
        return;
    }

    try {
        await navigator.clipboard.writeText(url);

        setMessage(
            copyMessage,
            "Copied to clipboard.",
            "success"
        );

        clearTimeout(copyMessageTimeout);

        copyMessageTimeout = setTimeout(() => {
            setMessage(copyMessage, "");
        }, 2500);

    } catch {
        setMessage(
            copyMessage,
            "Unable to copy. Please copy the URL manually.",
            "error"
        );
    }
}


form.addEventListener("submit", shortenUrl);

copyButton.addEventListener("click", copyShortUrl);

analyticsButton.addEventListener("click", loadAnalytics);

refreshButton.addEventListener("click", loadAnalytics);