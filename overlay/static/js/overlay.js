const POLL_INTERVAL_MS = 1000;
const ANIMATION_DURATION_MS = 4200;
const PAUSE_BETWEEN_EVENTS_MS = 250;
const MEMBER_NOTICE_DURATION_MS = 3000;

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

const memberRankingStage =
    document.getElementById("member-ranking-stage");
const memberRankingWheels =
    document.getElementById("ranking-wheels");

const likesRankingStage =
    document.getElementById("likes-ranking-stage");
const likesRankingWheels =
    document.getElementById("likes-ranking-wheels");

let animationRunning = false;
let pollingEnabled = true;
let overlayEventQueue = [];

const persistentRankings = {
    members: null,
    likes: null
};

const rankingFingerprints = {
    members: "",
    likes: ""
};

const overlayClientId =
    sessionStorage.getItem("pandaia-overlay-client-id") ||
    (
        window.crypto && window.crypto.randomUUID
            ? window.crypto.randomUUID()
            : `overlay-${Date.now()}-${Math.random()}`
    );

sessionStorage.setItem(
    "pandaia-overlay-client-id",
    overlayClientId
);

const overlayAccessToken =
    new URLSearchParams(window.location.search)
        .get("access") || "";


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
            if (
                value.startsWith("/gift-assets/") &&
                overlayAccessToken
            ) {
                const separator =
                    value.includes("?") ? "&" : "?";

                return (
                    `${value}${separator}access=` +
                    encodeURIComponent(overlayAccessToken)
                );
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


function rankingFingerprint(event, kind) {
    const rows = Array.isArray(event.members)
        ? event.members.slice(0, 3)
        : [];

    return JSON.stringify({
        kind,
        mode: String(event.mode || ""),
        position: String(event.position || ""),
        scale: Number(event.scale || 100),
        rows: rows.map((row) => ({
            user_id: String(row.user_id || ""),
            unique_id: String(row.unique_id || ""),
            nickname: String(row.nickname || ""),
            avatar: String(row.avatar || ""),
            current_level: Number(row.current_level || 0),
            likes: Number(row.likes || 0)
        }))
    });
}


function formatLikes(value) {
    const likes = Math.max(0, Number(value || 0));

    if (likes >= 1000000) {
        return `${(likes / 1000000).toFixed(1)}M`;
    }

    if (likes >= 1000) {
        return `${(likes / 1000).toFixed(1)}K`;
    }

    return String(likes);
}


function clearTransientAnimation() {
    giftContainer.classList.remove("visible");
    flashEffect.classList.remove("active");
    ambientLight.classList.remove("active");

    giftContainer.setAttribute("aria-hidden", "true");
    giftImage.removeAttribute("src");
    giftImage.alt = "";
    giftSender.textContent = "";
    giftName.textContent = "";

    memberStage.classList.remove(
        "visible",
        "member-notice-phase",
        "member-shuttle-phase"
    );
    memberStage.setAttribute("aria-hidden", "true");
    memberAvatar.removeAttribute("src");
}


function hideRankings() {
    memberRankingStage.classList.add(
        "ranking-temporarily-hidden"
    );
    likesRankingStage.classList.add(
        "ranking-temporarily-hidden"
    );

    memberRankingStage.setAttribute(
        "aria-hidden",
        "true"
    );
    likesRankingStage.setAttribute(
        "aria-hidden",
        "true"
    );
}


function showRankings() {
    if (persistentRankings.members) {
        memberRankingStage.classList.remove(
            "ranking-temporarily-hidden"
        );
        memberRankingStage.classList.add(
            "visible",
            "ranking-persistent"
        );
        memberRankingStage.setAttribute(
            "aria-hidden",
            "false"
        );
    }

    if (persistentRankings.likes) {
        likesRankingStage.classList.remove(
            "ranking-temporarily-hidden"
        );
        likesRankingStage.classList.add(
            "visible",
            "ranking-persistent"
        );
        likesRankingStage.setAttribute(
            "aria-hidden",
            "false"
        );
    }
}


function playLevelSound(event) {
    if (!event.sound) {
        return;
    }

    try {
        const AudioContext =
            window.AudioContext ||
            window.webkitAudioContext;

        const context = new AudioContext();
        const oscillator = context.createOscillator();
        const gain = context.createGain();

        oscillator.type = "sine";
        oscillator.frequency.setValueAtTime(
            220,
            context.currentTime
        );
        oscillator.frequency.exponentialRampToValueAtTime(
            880,
            context.currentTime + 1.4
        );

        gain.gain.setValueAtTime(
            Math.max(
                0,
                Math.min(
                    1,
                    Number(event.volume || 50) / 100
                )
            ) * 0.18,
            context.currentTime
        );

        gain.gain.exponentialRampToValueAtTime(
            0.001,
            context.currentTime + 1.7
        );

        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 1.7);
        oscillator.onended = () => context.close();
    } catch (error) {
        console.warn(
            "No se pudo reproducir el sonido del ascenso.",
            error
        );
    }
}


function preloadImage(imageUrl) {
    return new Promise((resolve, reject) => {
        const image = new Image();

        image.onload = () => resolve(imageUrl);
        image.onerror = () => reject(
            new Error(
                `No se pudo cargar la imagen: ${imageUrl}`
            )
        );
        image.src = imageUrl;
    });
}


function createRankingCard(row, index, kind) {
    const medals = [
        {place: 1, label: "1", tone: "gold"},
        {place: 2, label: "2", tone: "silver"},
        {place: 3, label: "3", tone: "bronze"}
    ];

    const medal = medals[index];
    const card = document.createElement("article");

    card.className = [
        "ranking-crown",
        `place-${medal.place}`,
        `crown-${medal.tone}`,
        `ranking-kind-${kind}`
    ].join(" ");

    const scene = document.createElement("div");
    scene.className = "crown-scene";

    const rotor = document.createElement("div");
    rotor.className = "crown-rotor";
    rotor.style.animationDelay = `${index * 0.55}s`;

    const metricFace = document.createElement("div");
    metricFace.className =
        "crown-face crown-level-face crown-metric-face";

    const decoration = document.createElement("div");
    decoration.className = "crown-shape";

    const place = document.createElement("b");
    place.className = "crown-place";
    place.textContent = medal.label;

    const metricLabel = document.createElement("small");
    metricLabel.textContent =
        kind === "likes" ? "LIKES" : "NIVEL";

    const metric = document.createElement("strong");
    metric.textContent =
        kind === "likes"
            ? formatLikes(row.likes)
            : String(row.current_level || 0);

    metricFace.append(
        decoration,
        place,
        metricLabel,
        metric
    );

    const avatarFace = document.createElement("div");
    avatarFace.className =
        "crown-face crown-avatar-face";

    const avatarDecoration =
        document.createElement("div");
    avatarDecoration.className = "crown-shape";

    const avatarFrame =
        document.createElement("div");
    avatarFrame.className = "crown-avatar-frame";

    const image = document.createElement("img");
    image.alt = "";
    image.decoding = "async";

    if (row.avatar) {
        image.src = row.avatar;
    }

    const fallback = document.createElement("span");
    fallback.className = "avatar-fallback";
    fallback.textContent = String(
        row.nickname ||
        row.unique_id ||
        "P"
    ).trim().charAt(0).toUpperCase() || "P";

    image.addEventListener("load", () => {
        fallback.style.display = "none";
    });

    avatarFrame.append(image, fallback);

    const avatarPlace =
        document.createElement("b");
    avatarPlace.className = "crown-place";
    avatarPlace.textContent = medal.label;

    avatarFace.append(
        avatarDecoration,
        avatarFrame,
        avatarPlace
    );

    rotor.append(metricFace, avatarFace);
    scene.append(rotor);

    const metricBadge =
        document.createElement("span");
    metricBadge.className = "ranking-metric-badge";
    metricBadge.textContent =
        kind === "likes"
            ? `♥ ${formatLikes(row.likes)}`
            : `♛ ${Number(row.current_level || 0)}`;

    const name = document.createElement("span");
    name.className = "crown-member-name";
    name.textContent =
        row.nickname ||
        row.unique_id ||
        (
            kind === "likes"
                ? "Seguidor"
                : "Miembro"
        );

    card.append(
        scene,
        metricBadge,
        name
    );

    return card;
}


function renderRanking(event, kind) {
    const isLikes = kind === "likes";
    const stage = isLikes
        ? likesRankingStage
        : memberRankingStage;
    const wheels = isLikes
        ? likesRankingWheels
        : memberRankingWheels;

    const fingerprint =
        rankingFingerprint(event, kind);

    if (
        fingerprint === rankingFingerprints[kind] &&
        wheels.childElementCount > 0
    ) {
        stage.classList.remove(
            "ranking-temporarily-hidden"
        );
        stage.classList.add(
            "visible",
            "ranking-persistent"
        );
        stage.setAttribute("aria-hidden", "false");
        return;
    }

    wheels.replaceChildren();

    const rows = Array.isArray(event.members)
        ? event.members.slice(0, 3)
        : [];

    rows.forEach((row, index) => {
        wheels.append(
            createRankingCard(row, index, kind)
        );
    });

    stage.style.setProperty(
        "--ranking-scale",
        `${Math.max(
            50,
            Math.min(
                150,
                Number(event.scale || 100)
            )
        ) / 100}`
    );

    stage.classList.remove(
        "ranking-temporarily-hidden",
        "ranking-top",
        "ranking-bottom"
    );

    stage.classList.add(
        "visible",
        "ranking-persistent"
    );

    stage.setAttribute("aria-hidden", "false");

    rankingFingerprints[kind] = fingerprint;
    persistentRankings[kind] = event;
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


function startGiftAnimation() {
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
    const rankingTypes = [
        "member_level_leaderboard",
        "like_leaderboard"
    ];

    if (rankingTypes.includes(event.type)) {
        renderRanking(
            event,
            event.type === "like_leaderboard"
                ? "likes"
                : "members"
        );
        return;
    }

    if (animationRunning) {
        return;
    }

    if (
        ![
            "gift",
            "member_level_up"
        ].includes(event.type)
    ) {
        return;
    }

    if (event.duration_ms) {
        document.documentElement.style.setProperty(
            "--animation-duration",
            `${Number(event.duration_ms)}ms`
        );
    }

    animationRunning = true;

    try {
        hideRankings();
        clearTransientAnimation();

        const duration = Math.max(
            1000,
            Number(
                event.duration_ms ||
                (
                    event.type === "gift"
                        ? ANIMATION_DURATION_MS
                        : 8000
                )
            )
        );

        document.documentElement.style.setProperty(
            "--member-duration",
            `${duration}ms`
        );

        if (event.type === "gift") {
            await prepareGift(event);
            startGiftAnimation();
            await sleep(duration);
        } else {
            const user = getSenderName(event)
                .replace(/^@/, "");

            memberTitle.textContent = String(
                event.message ||
                "¡FELICIDADES, @{user}!"
            ).replace("{user}", user);

            memberSubtitle.textContent =
                `ALCANZASTE EL NIVEL DE MIEMBRO ${
                    Number(event.new_level)
                }`;

            memberLevel.textContent =
                String(Number(event.new_level));

            const avatar =
                String(event.avatar_url || "");

            if (avatar) {
                memberAvatar.src = avatar;
            }

            memberStage.classList.add(
                "member-notice-phase"
            );
            memberStage.setAttribute(
                "aria-hidden",
                "false"
            );

            restartAnimation(
                memberStage,
                "visible"
            );

            await sleep(MEMBER_NOTICE_DURATION_MS);

            memberStage.classList.remove(
                "member-notice-phase"
            );
            memberStage.classList.add(
                "member-shuttle-phase"
            );

            playLevelSound(event);

            restartAnimation(
                memberStage,
                "visible"
            );

            await sleep(duration);
        }
    } catch (error) {
        console.error(
            "No se pudo reproducir el evento del overlay:",
            error,
            event
        );
    } finally {
        clearTransientAnimation();
        showRankings();
        await sleep(PAUSE_BETWEEN_EVENTS_MS);
        animationRunning = false;
    }
}


function queuePriority(type) {
    const priority = {
        "member_level_up": 0,
        "gift": 1,
        "member_level_leaderboard": 2,
        "like_leaderboard": 3,
    };

    return priority[type] ?? 9;
}


function enqueueEvent(event) {
    if (!event || typeof event !== "object") {
        return;
    }

    const type = String(event.type || "").trim();

    if (!type) {
        return;
    }

    overlayEventQueue.push(event);
    overlayEventQueue.sort((left, right) => {
        const leftPriority = queuePriority(left.type);
        const rightPriority = queuePriority(right.type);

        if (leftPriority !== rightPriority) {
            return leftPriority - rightPriority;
        }

        return 0;
    });
}


async function dequeueEvent() {
    const next = overlayEventQueue.shift();

    if (!next) {
        return null;
    }

    return next;
}


async function requestNextEvent() {
    if (!pollingEnabled) {
        return;
    }

    try {
        const response = await fetch(
            `/api/events/next?client_id=${
                encodeURIComponent(overlayClientId)
            }${
                overlayAccessToken
                    ? `&access=${
                        encodeURIComponent(
                            overlayAccessToken
                        )
                    }`
                    : ""
            }`,
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
            enqueueEvent(data.event);
        }
    } catch (error) {
        console.error(
            "No se pudo consultar la cola del overlay:",
            error
        );
    }
}


async function playbackLoop() {
    while (pollingEnabled) {
        const nextEvent = await dequeueEvent();

        if (nextEvent) {
            if (animationRunning) {
                enqueueEvent(nextEvent);
                await sleep(25);
                continue;
            }

            await playEvent(nextEvent);
        } else {
            await sleep(10);
        }
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


clearTransientAnimation();
pollingLoop();
playbackLoop();