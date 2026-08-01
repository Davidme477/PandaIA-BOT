const POLL_INTERVAL_MS = 1000;
const ANIMATION_DURATION_MS = 4200;
const PAUSE_BETWEEN_EVENTS_MS = 250;

const giftContainer = document.getElementById("gift-container");
const giftImage = document.getElementById("gift-image");
const giftSender = document.getElementById("gift-sender");
const giftName = document.getElementById("gift-name");
const flashEffect = document.getElementById("flash-effect");
const ambientLight = document.getElementById("ambient-light");

let animationRunning = false;
let pollingEnabled = true;
const overlayClientId = sessionStorage.getItem("pandaia-overlay-client-id") ||
    (window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : `overlay-${Date.now()}-${Math.random()}`);
sessionStorage.setItem("pandaia-overlay-client-id", overlayClientId);
const overlayAccessToken = new URLSearchParams(window.location.search).get("access") || "";


function sleep(milliseconds) {
    return new Promise((resolve) => {
        window.setTimeout(resolve, milliseconds);
    });
}


function restartAnimation(element, className) {
    element.classList.remove(className);

    void element.offsetWidth;

    element.classList.add(className);
}


function getEventImageUrl(event) {
    const possibleUrls = [
        event.image_url,
        event.content,
        event.gift_image,
        event.image,
        event.asset_url
    ];

    for (const possibleUrl of possibleUrls) {
        const value = String(possibleUrl || "").trim();

        if (
            value.startsWith("http://") ||
            value.startsWith("https://") ||
            value.startsWith("/") ||
            value.startsWith("data:image/")
        ) {
            if (value.startsWith("/gift-assets/") && overlayAccessToken) {
                const separator = value.includes("?") ? "&" : "?";
                return `${value}${separator}access=${encodeURIComponent(overlayAccessToken)}`;
            }
            return value;
        }
    }

    return "";
}


function getSenderName(event) {
    return String(
        event.sender_name ||
        event.nickname ||
        event.user_name ||
        event.username ||
        event.unique_id ||
        "Usuario de TikTok"
    ).trim();
}


function getGiftName(event) {
    return String(
        event.gift_name ||
        event.name ||
        "envió un regalo"
    ).trim();
}


function clearAnimation() {
    giftContainer.classList.remove("visible");
    flashEffect.classList.remove("active");
    ambientLight.classList.remove("active");

    giftContainer.setAttribute(
        "aria-hidden",
        "true"
    );

    giftImage.removeAttribute("src");
    giftImage.alt = "";

    giftSender.textContent = "";
    giftName.textContent = "";
}


function preloadImage(imageUrl) {
    return new Promise((resolve, reject) => {
        const image = new Image();

        image.onload = () => {
            resolve(imageUrl);
        };

        image.onerror = () => {
            reject(
                new Error(
                    `No se pudo cargar la imagen: ${imageUrl}`
                )
            );
        };

        image.src = imageUrl;
    });
}


async function prepareGift(event) {
    const imageUrl = getEventImageUrl(event);

    if (!imageUrl) {
        throw new Error(
            "El evento no contiene una imagen válida."
        );
    }

    await preloadImage(imageUrl);

    giftImage.src = imageUrl;
    giftImage.alt = getGiftName(event);

    giftSender.textContent = getSenderName(event);
    giftName.textContent = getGiftName(event);
}


function startAnimation() {
    giftContainer.setAttribute(
        "aria-hidden",
        "false"
    );

    restartAnimation(
        flashEffect,
        "active"
    );

    restartAnimation(
        ambientLight,
        "active"
    );

    restartAnimation(
        giftContainer,
        "visible"
    );
}


async function playEvent(event) {
    if (animationRunning) {
        return;
    }

    if (event.type !== "gift") return;
    if (event.duration_ms) document.documentElement.style.setProperty("--animation-duration", `${Number(event.duration_ms)}ms`);
    animationRunning = true;

    try {
        clearAnimation();

        await prepareGift(event);

        startAnimation();

        await sleep(ANIMATION_DURATION_MS);
    } catch (error) {
        console.error(
            "No se pudo reproducir el regalo:",
            error,
            event
        );
    } finally {
        clearAnimation();

        await sleep(PAUSE_BETWEEN_EVENTS_MS);

        animationRunning = false;
    }
}


async function requestNextEvent() {
    if (
        !pollingEnabled ||
        animationRunning
    ) {
        return;
    }

    try {
        const response = await fetch(
            `/api/events/next?client_id=${encodeURIComponent(overlayClientId)}${overlayAccessToken ? `&access=${encodeURIComponent(overlayAccessToken)}` : ""}`,
            {
                method: "GET",
                cache: "no-store",
                headers: {
                    "Accept": "application/json"
                }
            }
        );

        if (!response.ok) {
            console.warn(
                "El servidor respondió:",
                response.status
            );

            return;
        }

        const data = await response.json();

        if (data && data.event) {
            await playEvent(data.event);
        }
    } catch (error) {
        console.error(
            "No se pudo consultar la cola del overlay:",
            error
        );
    }
}


async function pollingLoop() {
    while (pollingEnabled) {
        await requestNextEvent();
        await sleep(POLL_INTERVAL_MS);
    }
}


window.addEventListener(
    "beforeunload",
    () => {
        pollingEnabled = false;
    }
);


clearAnimation();
pollingLoop();
