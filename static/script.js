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
const qrButton = document.getElementById("qr-button");
const analyticsButton = document.getElementById("analytics-button");
const copyMessage = document.getElementById("copy-message");
const qrPanel = document.getElementById("qr-panel");
const qrImage = document.getElementById("qr-image");
const qrMessage = document.getElementById("qr-message");

const linkStatus = document.getElementById("link-status");
const toggleLinkButton = document.getElementById("toggle-link-button");
const linkManagementMessage = document.getElementById(
    "link-management-message"
);

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
let currentLinkActive = true;
let copyMessageTimeout = null;
let analyticsMessageTimeout = null;
let qrImageObjectUrl = null;


/* ---------------------------------------------------------
   MESSAGE HELPERS
--------------------------------------------------------- */

function setMessage(element, message, type = "") {
    element.textContent = message;
    element.className = "message";

    if (type) {
        element.classList.add(`message-${type}`);
    }
}


function clearAnalyticsMessage() {
    clearTimeout(analyticsMessageTimeout);
    analyticsMessageTimeout = null;
    setMessage(analyticsMessage, "");
}


function showAnalyticsSuccess() {
    clearAnalyticsMessage();
    setMessage(
        analyticsMessage,
        "Analytics refreshed successfully.",
        "success"
    );

    analyticsMessageTimeout = setTimeout(() => {
        setMessage(analyticsMessage, "");
        analyticsMessageTimeout = null;
    }, 3000);
}


/* ---------------------------------------------------------
   BUTTON STATES
--------------------------------------------------------- */

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


function setQrState(isLoading) {
    qrButton.disabled = isLoading;
    qrButton.textContent = isLoading ? "Loading..." : "QR";
}


function setLinkManagementState(isLoading) {
    toggleLinkButton.disabled = isLoading;

    toggleLinkButton.textContent = isLoading
        ? "Updating..."
        : currentLinkActive
            ? "Deactivate"
            : "Reactivate";
}


/* ---------------------------------------------------------
   URL HELPERS
--------------------------------------------------------- */

function buildShortUrl(shortCode) {
    return `${window.location.origin}/${encodeURIComponent(shortCode)}`;
}


/* ---------------------------------------------------------
   LINK MANAGEMENT
--------------------------------------------------------- */

function updateLinkStatusUI(isActive) {
    currentLinkActive = isActive;

    linkStatus.textContent = isActive
        ? "Active"
        : "Deactivated";

    toggleLinkButton.textContent = isActive
        ? "Deactivate"
        : "Reactivate";
}


async function toggleLinkStatus() {
    if (!currentShortCode) {
        return;
    }

    const newStatus = !currentLinkActive;

    setMessage(linkManagementMessage, "");
    setLinkManagementState(true);

    try {
        const response = await fetch(
            `/${encodeURIComponent(currentShortCode)}`,
            {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    is_active: newStatus
                })
            }
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
                data.error || "Unable to update the short URL."
            );
        }

        updateLinkStatusUI(data.is_active);

        setMessage(
            linkManagementMessage,
            data.is_active
                ? "Short URL has been reactivated."
                : "Short URL has been deactivated.",
            "success"
        );

    } catch (error) {
        if (error instanceof TypeError) {
            setMessage(
                linkManagementMessage,
                "Unable to connect to the server. Please try again.",
                "error"
            );
        } else {
            setMessage(
                linkManagementMessage,
                error.message || "Unable to update the short URL.",
                "error"
            );
        }
    } finally {
        setLinkManagementState(false);
    }
}


/* ---------------------------------------------------------
   SUCCESS PANEL
--------------------------------------------------------- */

function showSuccess(shortCode) {
    const fullShortUrl = buildShortUrl(shortCode);

    shortUrlElement.textContent = fullShortUrl;
    shortUrlElement.href = fullShortUrl;
    openButton.href = fullShortUrl;

    updateLinkStatusUI(true);
    resetQrDisplay();
    setMessage(linkManagementMessage, "");

    successPanel.classList.remove("hidden");

    setMessage(formMessage, "Short URL created.", "success");
    setMessage(copyMessage, "");
}


function resetQrDisplay() {
    if (qrImageObjectUrl) {
        URL.revokeObjectURL(qrImageObjectUrl);
        qrImageObjectUrl = null;
    }

    qrImage.removeAttribute("src");
    qrImage.classList.add("hidden");
    qrPanel.classList.add("hidden");
    setMessage(qrMessage, "");
    setQrState(false);
}


async function loadQrCode() {
    if (!currentShortCode) {
        return;
    }

    setMessage(qrMessage, "");
    setQrState(true);

    try {
        const response = await fetch(
            `/${encodeURIComponent(currentShortCode)}/qr`
        );

        if (!response.ok) {
            if (response.status === 404) {
                throw new Error("This short URL could not be found.");
            }

            if (response.status === 403) {
                throw new Error("This short URL has been deactivated.");
            }

            if (response.status === 410) {
                throw new Error("This short URL has expired.");
            }

            throw new Error("Unable to generate the QR code.");
        }

        const imageBlob = await response.blob();

        if (qrImageObjectUrl) {
            URL.revokeObjectURL(qrImageObjectUrl);
        }

        qrImageObjectUrl = URL.createObjectURL(imageBlob);
        qrImage.src = qrImageObjectUrl;
        qrImage.classList.remove("hidden");
        qrPanel.classList.remove("hidden");

    } catch (error) {
        if (qrImageObjectUrl) {
            URL.revokeObjectURL(qrImageObjectUrl);
            qrImageObjectUrl = null;
        }

        qrImage.removeAttribute("src");
        qrImage.classList.add("hidden");
        qrPanel.classList.remove("hidden");

        if (error instanceof TypeError) {
            setMessage(
                qrMessage,
                "Unable to connect to the server. Please try again.",
                "error"
            );
        } else {
            setMessage(
                qrMessage,
                error.message || "Unable to generate the QR code.",
                "error"
            );
        }
    } finally {
        setQrState(false);
    }
}


/* ---------------------------------------------------------
   URL VALIDATION
--------------------------------------------------------- */

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


/* ---------------------------------------------------------
   EXPIRY HANDLING
--------------------------------------------------------- */

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


/* ---------------------------------------------------------
   SHORTEN URL
--------------------------------------------------------- */

async function shortenUrl(event) {
    event.preventDefault();

    const originalUrl = originalUrlInput.value.trim();
    const alias = aliasInput.value.trim();
    const expiresAt = expiresAtInput.value;

    setMessage(formMessage, "");
    setMessage(copyMessage, "");
    setMessage(linkManagementMessage, "");

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
        currentLinkActive = true;

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


/* ---------------------------------------------------------
   ANALYTICS
--------------------------------------------------------- */

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
    timelineElement.classList.remove("timeline-compact");

    if (!Array.isArray(clicksOverTime) || clicksOverTime.length === 0) {
        const emptyState = document.createElement("p");
        emptyState.className = "empty-state";
        emptyState.textContent = "No timeline data available.";

        timelineElement.appendChild(emptyState);
        return;
    }

    const clicksByDay = clicksOverTime.map(item => Number(item.clicks) || 0);
    const highestClickCount = Math.max(...clicksByDay);
    const chartScale = 10;

    timelineElement.classList.toggle(
        "timeline-compact",
        highestClickCount === 0
    );

    clicksOverTime.forEach((item, index) => {
        const clicks = clicksByDay[index];

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
            : Math.max(Math.min((clicks / chartScale) * 100, 100), 8);

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

        if (labelKey === "country") {
            emptyState.textContent = "Country data is unavailable yet.";
        } else {
            emptyState.textContent = "No referrer data available.";

            const explanation = document.createElement("p");
            explanation.className = "empty-state-description";
            explanation.textContent =
                "The source of a visit cannot be identified when referrer information isn't provided.";

            container.appendChild(emptyState);
            container.appendChild(explanation);
            return;
        }

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


async function loadAnalytics(showSuccess = false) {
    if (!currentShortCode) {
        return;
    }

    analyticsSection.classList.remove("hidden");
    analyticsUrl.textContent = buildShortUrl(currentShortCode);

    clearAnalyticsMessage();
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

        if (showSuccess) {
            showAnalyticsSuccess();
        }

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


/* ---------------------------------------------------------
   COPY SHORT URL
--------------------------------------------------------- */

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


/* ---------------------------------------------------------
   EVENT LISTENERS
--------------------------------------------------------- */

form.addEventListener("submit", shortenUrl);

copyButton.addEventListener("click", copyShortUrl);

qrButton.addEventListener("click", loadQrCode);

analyticsButton.addEventListener("click", () => loadAnalytics());

refreshButton.addEventListener("click", () => loadAnalytics(true));

toggleLinkButton.addEventListener("click", toggleLinkStatus);