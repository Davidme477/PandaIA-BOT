from __future__ import annotations

import re
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
HTML_FILE = PROJECT_ROOT / "overlay" / "templates" / "overlay.html"
CSS_FILE = PROJECT_ROOT / "overlay" / "static" / "css" / "overlay.css"
JS_FILE = PROJECT_ROOT / "overlay" / "static" / "js" / "overlay.js"

BACKUP_SUFFIX = ".bak_overlay_shuttle"


NEW_MEMBER_SECTION = r'''        <section id="member-level-stage" class="member-stage" aria-hidden="true">
            <div class="shuttle-space" aria-hidden="true">
                <i class="space-star star-1"></i>
                <i class="space-star star-2"></i>
                <i class="space-star star-3"></i>
                <i class="space-star star-4"></i>
                <i class="space-star star-5"></i>
                <div class="energy-ring ring-1"></div>
                <div class="energy-ring ring-2"></div>
            </div>

            <div id="member-particles" class="member-particles"></div>

            <div class="member-celebration">
                <div class="level-up-label">MEMBER LEVEL UP</div>
                <h1 id="member-title"></h1>

                <div class="member-badge">
                    <div class="badge-energy"></div>
                    <img id="member-avatar" alt="">
                    <strong id="member-level"></strong>
                </div>

                <h2 id="member-subtitle"></h2>
            </div>

            <div class="shuttle" aria-hidden="true">
                <div class="shuttle-glow"></div>
                <div class="shuttle-body">
                    <div class="shuttle-window"></div>
                    <div class="shuttle-fin fin-left"></div>
                    <div class="shuttle-fin fin-right"></div>
                    <div class="shuttle-engine"></div>
                </div>
                <div class="shuttle-flame flame-main"></div>
                <div class="shuttle-flame flame-left"></div>
                <div class="shuttle-flame flame-right"></div>
                <div class="shuttle-trail"></div>
            </div>

            <div class="member-burst" aria-hidden="true"></div>
        </section>'''


NEW_RENDER_RANKING = r'''function renderRanking(event) {
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

    rankingStage.style.setProperty(
        "--ranking-scale",
        `${Math.max(50, Math.min(150, Number(event.scale || 100))) / 100}`
    );

    rankingStage.classList.add(
        String(event.position).toLowerCase().includes("inferior")
            ? "ranking-bottom"
            : "ranking-top"
    );

    rankingStage.setAttribute("aria-hidden", "false");
    restartAnimation(rankingStage, "visible");
}'''


CSS_UPGRADE = r'''
/* PANDAIA OVERLAY — SHUTTLE LEVEL UP + TOP 3 GIRATORIO */

.member-stage {
    isolation: isolate;
    background:
        radial-gradient(circle at 50% 72%, rgba(80, 231, 255, 0.18), transparent 28%),
        radial-gradient(circle at 50% 28%, rgba(134, 74, 255, 0.24), transparent 42%),
        linear-gradient(180deg, rgba(4, 7, 28, 0.96), rgba(12, 4, 32, 0.93));
}

.member-stage::before {
    inset: -20%;
    background: conic-gradient(from 0deg, transparent, rgba(72,226,255,.2), transparent 28%, rgba(164,92,255,.22), transparent 58%, rgba(72,226,255,.16), transparent);
    filter: blur(12px);
    animation: shuttle-space-spin var(--member-duration, 8s) linear both;
}

.member-stage::after {
    content: "";
    position: absolute;
    inset: 0;
    z-index: 0;
    opacity: 0;
    background:
        linear-gradient(90deg, transparent 48%, rgba(255,255,255,.35) 50%, transparent 52%),
        radial-gradient(circle at center, rgba(255,255,255,.8), transparent 28%);
    mix-blend-mode: screen;
    animation: shuttle-screen-flash var(--member-duration, 8s) ease both;
}

.shuttle-space { position:absolute; inset:0; z-index:1; overflow:hidden; }
.space-star {
    position:absolute; width:7px; height:7px; border-radius:50%; opacity:0;
    background:white; box-shadow:0 0 12px 4px rgba(125,225,255,.9);
    animation:star-warp var(--member-duration,8s) linear both;
}
.star-1{left:12%;top:20%;animation-delay:.1s}
.star-2{left:78%;top:13%;animation-delay:.35s}
.star-3{left:25%;top:68%;animation-delay:.55s}
.star-4{left:88%;top:61%;animation-delay:.8s}
.star-5{left:52%;top:10%;animation-delay:1.05s}

.energy-ring {
    position:absolute; left:50%; top:63%; width:min(76vw,780px); aspect-ratio:1;
    border-radius:50%; border:3px solid rgba(101,227,255,.6);
    box-shadow:0 0 35px rgba(66,226,255,.5), inset 0 0 35px rgba(159,85,255,.3);
    opacity:0; transform:translate(-50%,-50%) scale(.1) rotateX(72deg);
    animation:energy-ring-rise var(--member-duration,8s) ease-out both;
}
.ring-2{width:min(54vw,560px);border-color:rgba(190,106,255,.62);animation-delay:.28s}

.member-celebration {
    z-index:6;
    gap:clamp(8px,1.5vh,20px);
    transform-origin:center;
    text-shadow:0 0 15px rgba(88,230,255,.85),0 0 38px rgba(130,73,255,.8);
    animation:shuttle-member-copy var(--member-duration,8s) cubic-bezier(.2,.75,.2,1) both;
}
.level-up-label{
    padding:.35em 1.15em;border:1px solid rgba(132,232,255,.8);border-radius:999px;
    font-size:clamp(12px,1.7vw,25px);font-weight:900;letter-spacing:.24em;color:#dffbff;
    background:linear-gradient(90deg,rgba(35,183,255,.22),rgba(148,73,255,.28));
    box-shadow:0 0 22px rgba(72,222,255,.45)
}
.member-celebration h1{max-width:92vw;margin:0;font-size:clamp(30px,5.2vw,84px);line-height:1.02;text-transform:uppercase}
.member-celebration h2{
    margin:0;font-size:clamp(27px,4.5vw,72px);line-height:1;
    background:linear-gradient(180deg,#fff,#75efff 48%,#9b7cff);
    -webkit-background-clip:text;background-clip:text;color:transparent
}
.member-badge{
    width:clamp(178px,23vw,360px);padding:10px;border:2px solid rgba(255,255,255,.72);
    background:conic-gradient(from 45deg,#5bf1ff,#804dff,#ff68dd,#ffe277,#5bf1ff);
    box-shadow:0 0 26px rgba(82,231,255,.9),0 0 70px rgba(132,70,255,.7);
    animation:badge-hover 1.8s ease-in-out infinite alternate
}
.badge-energy{
    position:absolute;inset:-12%;border-radius:50%;border:3px dashed rgba(129,236,255,.72);
    animation:badge-energy-spin 3s linear infinite
}
.member-badge img{position:relative;z-index:2;border:4px solid rgba(7,13,39,.9)}
.member-badge strong{
    z-index:4;right:-5%;bottom:-1%;width:34%;border:4px solid #7ef4ff;
    background:linear-gradient(145deg,#111832,#28174f);color:white;
    box-shadow:0 0 24px rgba(84,232,255,.85)
}
.rocket{display:none!important}

.shuttle{
    position:absolute;z-index:5;left:50%;bottom:-38vh;width:clamp(105px,15vw,230px);
    height:clamp(190px,29vw,430px);transform:translateX(-50%);
    filter:drop-shadow(0 0 30px rgba(70,229,255,.75));
    animation:shuttle-launch var(--member-duration,8s) cubic-bezier(.25,.05,.3,1) both
}
.shuttle-glow{
    position:absolute;left:50%;top:42%;width:230%;aspect-ratio:1;border-radius:50%;
    transform:translate(-50%,-50%);
    background:radial-gradient(circle,rgba(119,238,255,.68),rgba(136,65,255,.28) 34%,transparent 68%);
    filter:blur(20px);animation:shuttle-glow-pulse .65s ease-in-out infinite alternate
}
.shuttle-body{
    position:absolute;left:50%;top:0;width:56%;height:70%;transform:translateX(-50%);
    border-radius:52% 52% 28% 28%/27% 27% 17% 17%;
    background:linear-gradient(90deg,#bec9df,#fff 38%,#a9b9d7 68%,#eef5ff);
    border:2px solid rgba(255,255,255,.85);
    box-shadow:inset -14px 0 20px rgba(58,75,122,.28),inset 12px 0 18px rgba(255,255,255,.72)
}
.shuttle-body::before{
    content:"";position:absolute;left:50%;top:-15%;width:72%;height:38%;transform:translateX(-50%);
    clip-path:polygon(50% 0,100% 100%,0 100%);
    background:linear-gradient(90deg,#c7d4eb,#fff,#9daecc)
}
.shuttle-body::after{
    content:"";position:absolute;left:50%;bottom:10%;width:36%;height:12%;transform:translateX(-50%);
    border-radius:999px;background:#7654ff;box-shadow:0 0 18px #4fe9ff
}
.shuttle-window{
    position:absolute;left:50%;top:19%;width:50%;aspect-ratio:1;transform:translateX(-50%);
    border-radius:50%;border:5px solid #4b5577;
    background:radial-gradient(circle at 35% 30%,#e8ffff 0 7%,#69dfff 20%,#244a91 62%,#11182f);
    box-shadow:0 0 16px rgba(83,225,255,.9)
}
.shuttle-fin{position:absolute;bottom:-2%;width:48%;height:40%;background:linear-gradient(180deg,#7d63ff,#342379);border:2px solid rgba(179,173,255,.7)}
.fin-left{left:-34%;clip-path:polygon(100% 0,100% 100%,0 88%)}
.fin-right{right:-34%;clip-path:polygon(0 0,100% 88%,0 100%)}
.shuttle-engine{position:absolute;left:50%;bottom:-9%;width:46%;height:15%;transform:translateX(-50%);border-radius:0 0 45% 45%;background:#1e2847;border:3px solid #7080ad}
.shuttle-flame{
    position:absolute;z-index:-1;top:65%;border-radius:50% 50% 65% 65%;
    transform-origin:top center;filter:blur(3px);animation:flame-dance .18s ease-in-out infinite alternate
}
.flame-main{left:50%;width:35%;height:54%;transform:translateX(-50%);background:linear-gradient(#fff,#72f3ff 20%,#6e5dff 58%,rgba(142,50,255,0))}
.flame-left,.flame-right{width:22%;height:42%;background:linear-gradient(#fff,#4ce8ff 24%,rgba(105,69,255,0))}
.flame-left{left:15%;transform:rotate(10deg)}
.flame-right{right:15%;transform:rotate(-10deg)}
.shuttle-trail{
    position:absolute;z-index:-2;left:50%;top:70%;width:120%;height:110vh;transform:translateX(-50%);
    clip-path:polygon(40% 0,60% 0,100% 100%,0 100%);
    background:linear-gradient(180deg,rgba(255,255,255,.72),rgba(72,229,255,.4) 12%,rgba(121,69,255,.24) 40%,transparent 80%);
    filter:blur(14px)
}
.member-burst{z-index:3;top:9%;width:clamp(80px,12vw,180px);box-shadow:0 0 55px 28px white,0 0 115px 72px #67eaff,0 0 180px 110px #814fff}

/* TOP 3 GIRATORIO */
.ranking-stage{padding:2vh 2vw;overflow:visible}
.ranking-wheels{
    width:100%;display:flex;align-items:flex-start;justify-content:center;
    gap:clamp(10px,2.6vw,45px);margin:3vh auto;perspective:1300px
}
.ranking-crown{
    position:relative;width:clamp(150px,19vw,330px);text-align:center;
    animation:crown-card-entry var(--ranking-duration,12s) ease both
}
.ranking-crown.place-1{order:2;width:clamp(180px,23vw,390px)}
.ranking-crown.place-2{order:1;transform:translateY(5vh)}
.ranking-crown.place-3{order:3;transform:translateY(7vh)}
.crown-scene{width:100%;aspect-ratio:.88;perspective:1000px}
.crown-rotor{
    position:relative;width:100%;height:100%;transform-style:preserve-3d;
    animation:crown-turn 5.6s cubic-bezier(.45,.05,.55,.95) infinite
}
.crown-face{
    position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
    backface-visibility:hidden;-webkit-backface-visibility:hidden;
    border-radius:27% 27% 42% 42%/22% 22% 29% 29%;
    border:3px solid var(--crown-light);
    background:radial-gradient(circle at 50% 35%,rgba(255,255,255,.32),transparent 28%),linear-gradient(145deg,var(--crown-bright),var(--crown-dark));
    box-shadow:0 0 28px var(--crown-glow),inset 0 0 25px rgba(255,255,255,.22),inset 0 -22px 30px rgba(0,0,0,.26);
    overflow:hidden
}
.crown-face::after{content:"";position:absolute;inset:4%;border:1px solid rgba(255,255,255,.35);border-radius:inherit;pointer-events:none}
.crown-avatar-face{transform:rotateY(180deg)}
.crown-shape{
    position:absolute;left:4%;right:4%;top:-17%;height:48%;
    clip-path:polygon(0 100%,5% 28%,25% 62%,40% 8%,53% 60%,72% 3%,84% 61%,100% 25%,95% 100%);
    background:linear-gradient(90deg,var(--crown-dark),var(--crown-light) 42%,var(--crown-bright) 61%,var(--crown-dark));
    border-bottom:5px solid rgba(255,255,255,.45);filter:drop-shadow(0 0 12px var(--crown-glow))
}
.crown-place{position:relative;z-index:2;margin-top:16%;font-size:clamp(16px,2.3vw,34px);letter-spacing:.08em;color:white;text-shadow:0 2px 8px rgba(0,0,0,.65)}
.crown-level-face small{position:relative;z-index:2;margin-top:.35em;font-size:clamp(12px,1.5vw,22px);font-weight:900;letter-spacing:.2em;color:rgba(255,255,255,.78)}
.crown-level-face strong{position:relative;z-index:2;font-size:clamp(60px,9vw,150px);line-height:.92;color:white;text-shadow:0 3px 0 rgba(0,0,0,.3),0 0 25px rgba(255,255,255,.65)}
.crown-avatar-frame{
    position:relative;z-index:3;width:61%;aspect-ratio:1;margin-top:14%;border-radius:50%;
    display:grid;place-items:center;overflow:hidden;border:6px solid rgba(255,255,255,.82);
    background:radial-gradient(circle,#3c3657,#121220);
    box-shadow:0 0 0 5px var(--crown-dark),0 0 28px var(--crown-glow)
}
.crown-avatar-frame img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.avatar-fallback{font-size:clamp(48px,8vw,115px);font-weight:900;color:white}
.crown-avatar-face .crown-place{margin-top:.55em}
.crown-member-name{
    display:block;width:120%;margin-left:-10%;margin-top:.7em;overflow:hidden;
    font-size:clamp(18px,2.6vw,40px);font-weight:900;line-height:1.1;color:white;
    text-overflow:ellipsis;white-space:nowrap;
    text-shadow:0 0 12px var(--crown-glow),0 3px 7px rgba(0,0,0,.8)
}
.crown-gold{--crown-light:#fff3a5;--crown-bright:#ffd84f;--crown-dark:#9b5c00;--crown-glow:rgba(255,211,62,.9)}
.crown-silver{--crown-light:#fff;--crown-bright:#dfe9f5;--crown-dark:#657387;--crown-glow:rgba(213,231,255,.85)}
.crown-bronze{--crown-light:#ffd1a6;--crown-bright:#d88748;--crown-dark:#69351c;--crown-glow:rgba(218,119,58,.85)}

@keyframes shuttle-space-spin{0%{opacity:0;transform:rotate(0) scale(.6)}14%,82%{opacity:1}100%{opacity:0;transform:rotate(110deg) scale(1.35)}}
@keyframes shuttle-screen-flash{0%,67%,100%{opacity:0}73%{opacity:.85}80%{opacity:0}}
@keyframes star-warp{0%,14%{opacity:0;transform:translateY(15vh) scale(.2)}22%{opacity:1}68%{opacity:.95;transform:translateY(-75vh) scale(1.7)}78%,100%{opacity:0;transform:translateY(-110vh) scale(2.2)}}
@keyframes energy-ring-rise{0%,16%{opacity:0;transform:translate(-50%,-50%) scale(.1) rotateX(72deg)}27%{opacity:.95}70%{opacity:.5;transform:translate(-50%,-50%) scale(1.3) rotateX(72deg)}88%,100%{opacity:0;transform:translate(-50%,-50%) scale(1.7) rotateX(72deg)}}
@keyframes shuttle-member-copy{0%,10%{opacity:0;transform:translateY(34px) scale(.72);filter:blur(10px)}20%{opacity:1;transform:translateY(0) scale(1.05);filter:blur(0)}28%,72%{opacity:1;transform:translateY(0) scale(1)}82%,100%{opacity:0;transform:translateY(-25px) scale(.88);filter:blur(7px)}}
@keyframes badge-hover{from{transform:translateY(-4px) rotate(-1deg)}to{transform:translateY(5px) rotate(1deg)}}
@keyframes badge-energy-spin{to{transform:rotate(360deg)}}
@keyframes shuttle-launch{0%,24%{opacity:0;transform:translateX(-50%) translateY(0) scale(.72)}29%{opacity:1;transform:translateX(-50%) translateY(-10vh) scale(.94)}52%{opacity:1;transform:translateX(-50%) translateY(-50vh) scale(1.04)}69%{opacity:1;transform:translateX(-50%) translateY(-92vh) scale(.88)}80%,100%{opacity:0;transform:translateX(-50%) translateY(-155vh) scale(.42)}}
@keyframes shuttle-glow-pulse{from{opacity:.42;transform:translate(-50%,-50%) scale(.86)}to{opacity:.95;transform:translate(-50%,-50%) scale(1.16)}}
@keyframes flame-dance{from{filter:blur(2px);opacity:.75}to{filter:blur(5px);opacity:1}}
@keyframes crown-card-entry{0%,7%{opacity:0;filter:blur(12px)}14%{opacity:1;filter:blur(0)}90%{opacity:1}100%{opacity:0}}
@keyframes crown-turn{0%,31%{transform:rotateY(0)}42%,71%{transform:rotateY(180deg)}82%,100%{transform:rotateY(360deg)}}

@media (orientation:landscape){
    .member-celebration{transform:scale(.76)}
    .shuttle{width:clamp(90px,11vw,165px);height:clamp(165px,22vw,300px)}
    .ranking-crown{max-width:225px}
    .ranking-crown.place-1{max-width:270px}
}
@media (max-width:600px){
    .ranking-wheels{gap:8px}
    .ranking-crown{width:29vw}
    .ranking-crown.place-1{width:34vw}
    .crown-face{border-width:2px}
    .crown-avatar-frame{border-width:3px}
}
'''


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def replace_member_section(html: str) -> str:
    pattern = re.compile(
        r'\s*<section id="member-level-stage".*?</section>\s*'
        r'(?=<section id="member-ranking-stage")',
        re.DOTALL,
    )
    updated, count = pattern.subn("\n" + NEW_MEMBER_SECTION + "\n        ", html, count=1)
    if count != 1:
        raise RuntimeError("No se encontró la sección estable de subida de nivel.")
    return updated


def replace_ranking_renderer(js: str) -> str:
    pattern = re.compile(
        r"function renderRanking\(event\) \{.*?\n\}\n\n\nasync function prepareGift",
        re.DOTALL,
    )
    replacement = NEW_RENDER_RANKING + "\n\n\nasync function prepareGift"
    updated, count = pattern.subn(replacement, js, count=1)
    if count != 1:
        raise RuntimeError("No se encontró renderRanking(event) en overlay.js.")
    return updated


def install() -> None:
    files = (HTML_FILE, CSS_FILE, JS_FILE)
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        print("ERROR: faltan archivos del overlay:")
        for item in missing:
            print(f"  - {item}")
        print("\nColoca este instalador en C:\\PandaIA BOT")
        raise SystemExit(1)

    for path in files:
        backup(path)

    html = replace_member_section(HTML_FILE.read_text(encoding="utf-8"))
    js = replace_ranking_renderer(JS_FILE.read_text(encoding="utf-8"))
    css = CSS_FILE.read_text(encoding="utf-8")

    marker = "PANDAIA OVERLAY — SHUTTLE LEVEL UP + TOP 3 GIRATORIO"
    if marker not in css:
        css = css.rstrip() + "\n\n" + CSS_UPGRADE.strip() + "\n"

    HTML_FILE.write_text(html, encoding="utf-8")
    JS_FILE.write_text(js, encoding="utf-8")
    CSS_FILE.write_text(css, encoding="utf-8")

    print("==============================================")
    print("OVERLAY MEJORADO CORRECTAMENTE")
    print("==============================================")
    print("Solo se modificaron:")
    print("  overlay/templates/overlay.html")
    print("  overlay/static/css/overlay.css")
    print("  overlay/static/js/overlay.js")
    print()
    print("Se crearon copias .bak_overlay_shuttle.")


if __name__ == "__main__":
    try:
        install()
    except Exception as error:
        print(f"\nERROR: {error}")
        raise SystemExit(1)