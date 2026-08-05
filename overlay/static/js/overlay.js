const POLL_INTERVAL_MS = 1000;
const ANIMATION_DURATION_MS = 4200;
const PAUSE_BETWEEN_EVENTS_MS = 250;

const giftContainer = document.getElementById("gift-container");
const giftImage = document.getElementById("gift-image");
const giftSender = document.getElementById("gift-sender");
const giftName = document.getElementById("gift-name");
const flashEffect = document.getElementById("flash-effect");
const ambientLight = document.getElementById("ambient-light");
const memberStage = document.getElementById("member-level-stage");
const memberTitle = document.getElementById("member-title");
const memberSubtitle = document.getElementById("member-subtitle");
const memberAvatar = document.getElementById("member-avatar");
const memberLevel = document.getElementById("member-level");
const rankingStage = document.getElementById("member-ranking-stage");
const rankingWheels = document.getElementById("ranking-wheels");

let animationRunning = false;
let persistentRankingEvent = null;
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


function clearAnimation({keepRanking = false} = {}) {
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

    memberStage.classList.remove("visible");
    memberStage.setAttribute("aria-hidden", "true");
    memberAvatar.removeAttribute("src");

    if (!keepRanking) {
        rankingStage.classList.remove(
            "visible",
            "ranking-top",
            "ranking-bottom",
            "ranking-persistent"
        );
        rankingStage.setAttribute("aria-hidden", "true");
        rankingWheels.replaceChildren();
    }
}

function playLevelSound(event) {
    if (!event.sound) return;
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        const context = new AudioContext(); const oscillator = context.createOscillator(); const gain = context.createGain();
        oscillator.type = "sine"; oscillator.frequency.setValueAtTime(220, context.currentTime);
        oscillator.frequency.exponentialRampToValueAtTime(880, context.currentTime + 1.4);
        gain.gain.setValueAtTime(Math.max(0, Math.min(1, Number(event.volume || 50) / 100)) * 0.18, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 1.7);
        oscillator.connect(gain); gain.connect(context.destination); oscillator.start(); oscillator.stop(context.currentTime + 1.7);
        oscillator.onended = () => context.close();
    } catch (error) { console.warn("No se pudo reproducir el sonido del ascenso.", error); }
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

function renderRanking(event) {
    rankingWheels.replaceChildren();

    const members = Array.isArray(event.members)
        ? event.members.slice(0, 3)
        : [];

    const medals = [
        {place: 1, label: "TOP 1", tone: "gold"},
        {place: 2, label: "TOP 2", tone: "silver"},
        {place: 3, label: "TOP 3", tone: "bronze"}
    ];

    members.forEach((member, index) => {
        const medal = medals[index];

        const card = document.createElement("article");
        card.className = `ranking-crown place-${medal.place} crown-${medal.tone}`;

        const scene = document.createElement("div");
        scene.className = "crown-scene";

        const rotor = document.createElement("div");
        rotor.className = "crown-rotor";
        rotor.style.animationDelay = `${index * 0.55}s`;

        const levelFace = document.createElement("div");
        levelFace.className = "crown-face crown-level-face";

        const levelCrown = document.createElement("div");
        levelCrown.className = "crown-shape";

        const place = document.createElement("b");
        place.className = "crown-place";
        place.textContent = medal.label;

        const levelLabel = document.createElement("small");
        levelLabel.textContent = "NIVEL";

        const level = document.createElement("strong");
        level.textContent = String(member.current_level || 0);

        levelFace.append(levelCrown, place, levelLabel, level);

        const avatarFace = document.createElement("div");
        avatarFace.className = "crown-face crown-avatar-face";

        const avatarCrown = document.createElement("div");
        avatarCrown.className = "crown-shape";

        const avatarFrame = document.createElement("div");
        avatarFrame.className = "crown-avatar-frame";

        const image = document.createElement("img");
        image.alt = "";
        image.decoding = "async";
        if (member.avatar) {
            image.src = member.avatar;
        }

        const avatarFallback = document.createElement("span");
        avatarFallback.className = "avatar-fallback";
        avatarFallback.textContent = String(
            member.nickname || member.unique_id || "M"
        ).trim().charAt(0).toUpperCase() || "M";

        image.addEventListener("load", () => {
            avatarFallback.style.display = "none";
        });

        avatarFrame.append(image, avatarFallback);

        const avatarPlace = document.createElement("b");
        avatarPlace.className = "crown-place";
        avatarPlace.textContent = medal.label;

        avatarFace.append(avatarCrown, avatarFrame, avatarPlace);
        rotor.append(levelFace, avatarFace);
        scene.append(rotor);

        const name = document.createElement("span");
        name.className = "crown-member-name";
        name.textContent = member.nickname || member.unique_id || "Miembro";

        card.append(scene, name);
        rankingWheels.append(card);
    });

    const isPersistent = String(event.mode || "")
        .toLowerCase()
        .includes("siempre");

    rankingStage.classList.toggle(
        "ranking-persistent",
        isPersistent
    );

    rankingStage.style.setProperty(
        "--ranking-scale",
        `${Math.max(50, Math.min(150, Number(event.scale || 100))) / 100}`
    );

    rankingStage.classList.remove(
        "ranking-top",
        "ranking-bottom"
    );

    rankingStage.classList.add(
        String(event.position).toLowerCase().includes("inferior")
            ? "ranking-bottom"
            : "ranking-top"
    );

    rankingStage.setAttribute("aria-hidden", "false");
    restartAnimation(rankingStage, "visible");
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

    if (!["gift", "member_level_up", "member_level_leaderboard"].includes(event.type)) return;
    if (event.duration_ms) document.documentElement.style.setProperty("--animation-duration", `${Number(event.duration_ms)}ms`);
    animationRunning = true;

    try {
        clearAnimation();

        const duration = Math.max(1000, Number(event.duration_ms || (event.type === "gift" ? ANIMATION_DURATION_MS : 8000)));
        document.documentElement.style.setProperty("--member-duration", `${duration}ms`);
        document.documentElement.style.setProperty("--ranking-duration", `${duration}ms`);
        if (event.type === "gift") {
            await prepareGift(event); startAnimation();
        } else if (event.type === "member_level_up") {
            playLevelSound(event);
            const user = getSenderName(event).replace(/^@/, "");
            memberTitle.textContent = String(event.message || "¡FELICIDADES, @{user}!").replace("{user}", user);
            memberSubtitle.textContent = `ALCANZASTE EL NIVEL DE MIEMBRO ${Number(event.new_level)}`;
            memberLevel.textContent = String(Number(event.new_level));
            const avatar = String(event.avatar_url || ""); if (avatar) memberAvatar.src = avatar;
            memberStage.setAttribute("aria-hidden", "false"); restartAnimation(memberStage, "visible");
        } else {
            const isPersistentRanking =
                String(event.mode || "")
                    .toLowerCase()
                    .includes("siempre");

            if (isPersistentRanking) {
                persistentRankingEvent = event;
            }

            renderRanking(event);

            if (isPersistentRanking) {
                return;
            }
        }

        await sleep(duration);
    } catch (error) {
        console.error(
            "No se pudo reproducir el regalo:",
            error,
            event
        );
    } finally {
        const permanentRankingWasShown =
            event.type === "member_level_leaderboard" &&
            persistentRankingEvent === event;

        if (!permanentRankingWasShown) {
            clearAnimation();

            if (persistentRankingEvent) {
                renderRanking(persistentRankingEvent);
            }

            await sleep(PAUSE_BETWEEN_EVENTS_MS);
        }

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