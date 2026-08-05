from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CSS_FILE = ROOT / "overlay" / "static" / "css" / "overlay.css"
JS_FILE = ROOT / "overlay" / "static" / "js" / "overlay.js"
BACKUP_SUFFIX = ".bak_linea_naranja_top_derecha"

CSS_MARKER = "PANDAIA AJUSTE - LINEA NARANJA + TOP DERECHO"

CSS_PATCH = r'''
/* PANDAIA AJUSTE - LINEA NARANJA + TOP DERECHO */

.member-celebration h2 {
    position: relative;
    width: min(88vw, 980px);
    min-height: clamp(64px, 9vh, 120px);
    margin: clamp(8px, 1.6vh, 20px) 0 0;
    padding: clamp(12px, 1.8vh, 24px) clamp(32px, 5vw, 72px);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: visible;
    border-top: 3px solid #ffb12b;
    border-bottom: 3px solid #ff7a00;
    border-radius: 10px;
    background:
        linear-gradient(
            90deg,
            transparent 0%,
            rgba(255, 105, 0, 0.2) 12%,
            rgba(255, 137, 0, 0.72) 50%,
            rgba(255, 105, 0, 0.2) 88%,
            transparent 100%
        );
    color: #fff6dc;
    -webkit-text-fill-color: #fff6dc;
    font-size: clamp(24px, 4vw, 66px);
    font-weight: 950;
    letter-spacing: .025em;
    text-transform: uppercase;
    text-shadow:
        0 2px 0 rgba(82, 28, 0, .95),
        0 0 12px #ff8b00,
        0 0 28px rgba(255, 92, 0, .9);
    box-shadow:
        0 0 18px rgba(255, 128, 0, .95),
        0 0 55px rgba(255, 79, 0, .62),
        inset 0 0 28px rgba(255, 167, 44, .28);
    clip-path: polygon(
        0 50%,
        5% 0,
        95% 0,
        100% 50%,
        95% 100%,
        5% 100%
    );
    animation:
        orange-level-line
        var(--member-duration, 8s)
        cubic-bezier(.2, .8, .2, 1)
        both;
}

.member-celebration h2::before,
.member-celebration h2::after {
    content: "";
    position: absolute;
    top: 50%;
    width: min(18vw, 220px);
    height: 5px;
    border-radius: 999px;
    transform: translateY(-50%) scaleX(0);
    background:
        linear-gradient(
            90deg,
            transparent,
            #ff7600 25%,
            #fff2b0 75%,
            #ff7600
        );
    box-shadow:
        0 0 10px #ff8a00,
        0 0 24px rgba(255, 93, 0, .95);
    animation:
        orange-side-line
        var(--member-duration, 8s)
        ease-out
        both;
}

.member-celebration h2::before {
    right: calc(100% - 5px);
    transform-origin: right center;
}

.member-celebration h2::after {
    left: calc(100% - 5px);
    transform-origin: left center;
}

.ranking-stage,
.ranking-stage.ranking-bottom {
    inset: 0;
    padding: 2.5vh 1.4vw 2.5vh 0;
    align-items: center;
    justify-content: flex-end;
    transform: scale(var(--ranking-scale, 1));
    transform-origin: center right;
}

.ranking-wheels,
.ranking-bottom .ranking-wheels {
    width: clamp(150px, 18vw, 300px);
    height: auto;
    max-height: 94vh;
    margin: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: clamp(8px, 1.5vh, 18px);
    perspective: 1100px;
}

.ranking-crown,
.ranking-crown.place-1,
.ranking-crown.place-2,
.ranking-crown.place-3 {
    order: initial;
    width: clamp(105px, 13vw, 215px);
    max-width: none;
    transform: none;
    margin: 0;
}

.ranking-crown.place-1 {
    width: clamp(120px, 14.5vw, 235px);
    order: 1;
}

.ranking-crown.place-2 {
    order: 2;
}

.ranking-crown.place-3 {
    order: 3;
}

.crown-scene {
    aspect-ratio: .9;
}

.crown-member-name {
    width: 108%;
    margin-left: -4%;
    margin-top: .3em;
    font-size: clamp(13px, 1.6vw, 27px);
}

.crown-place {
    font-size: clamp(12px, 1.5vw, 24px);
}

.crown-level-face small {
    font-size: clamp(9px, 1vw, 16px);
}

.crown-level-face strong {
    font-size: clamp(42px, 6vw, 88px);
}

.avatar-fallback {
    font-size: clamp(32px, 5vw, 70px);
}

@keyframes orange-level-line {
    0%, 8% {
        opacity: 0;
        transform: scaleX(.05) translateY(15px);
        filter: blur(8px);
    }

    16% {
        opacity: 1;
        transform: scaleX(1.03) translateY(0);
        filter: blur(0);
    }

    24%, 52% {
        opacity: 1;
        transform: scaleX(1) translateY(0);
    }

    61%, 100% {
        opacity: 0;
        transform: scaleX(.82) translateY(-18px);
        filter: blur(5px);
    }
}

@keyframes orange-side-line {
    0%, 9% {
        opacity: 0;
        transform: translateY(-50%) scaleX(0);
    }

    17%, 50% {
        opacity: 1;
        transform: translateY(-50%) scaleX(1);
    }

    60%, 100% {
        opacity: 0;
        transform: translateY(-50%) scaleX(.25);
    }
}

@media (max-width: 700px) {
    .ranking-stage,
    .ranking-stage.ranking-bottom {
        padding-right: 1vw;
    }

    .ranking-wheels,
    .ranking-bottom .ranking-wheels {
        width: 23vw;
        gap: 1vh;
    }

    .ranking-crown,
    .ranking-crown.place-1,
    .ranking-crown.place-2,
    .ranking-crown.place-3 {
        width: 21vw;
    }

    .ranking-crown.place-1 {
        width: 23vw;
    }

    .member-celebration h2 {
        width: 84vw;
        padding-left: 18px;
        padding-right: 18px;
    }

    .member-celebration h2::before,
    .member-celebration h2::after {
        width: 9vw;
    }
}
'''


def backup(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)


def patch_js(js: str) -> str:
    old = 'memberSubtitle.textContent = `¡SUBISTE AL NIVEL ${Number(event.new_level)}!`;'
    new = 'memberSubtitle.textContent = `ALCANZASTE EL NIVEL DE MIEMBRO ${Number(event.new_level)}`;'

    if new in js:
        return js

    if old not in js:
        raise RuntimeError(
            "No se encontró el texto actual de subida de nivel en overlay.js."
        )

    return js.replace(old, new, 1)


def main() -> None:
    if not CSS_FILE.is_file() or not JS_FILE.is_file():
        raise RuntimeError(
            "Coloca este archivo dentro de C:\\PandaIA BOT, junto a main.py."
        )

    css = CSS_FILE.read_text(encoding="utf-8")
    js = JS_FILE.read_text(encoding="utf-8")

    if "PANDAIA OVERLAY — SHUTTLE LEVEL UP + TOP 3 GIRATORIO" not in css:
        raise RuntimeError(
            "No se encontró el overlay mejorado. No se modificó nada."
        )

    backup(CSS_FILE)
    backup(JS_FILE)

    js = patch_js(js)

    if CSS_MARKER not in css:
        css = css.rstrip() + "\n\n" + CSS_PATCH.strip() + "\n"

    JS_FILE.write_text(js, encoding="utf-8")
    CSS_FILE.write_text(css, encoding="utf-8")

    print("==============================================")
    print("AJUSTE APLICADO CORRECTAMENTE")
    print("==============================================")
    print("Cambios realizados:")
    print("- Línea central naranja con el nuevo nivel.")
    print("- Texto: ALCANZASTE EL NIVEL DE MIEMBRO X.")
    print("- La nave actual se mantiene sin cambios.")
    print("- Top 3 ubicado verticalmente a la derecha.")
    print("- Regalos no modificados.")
    print()
    print("Copias de seguridad creadas automáticamente.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}")
        raise SystemExit(1)