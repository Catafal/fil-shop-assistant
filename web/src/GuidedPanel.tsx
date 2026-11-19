import { useEffect, useRef } from "react";
import { localizeTree, type Locale } from "./localization";
import { date, euro } from "./safety";
import type { GuidedAction, GuidedScenario, GuidedState, Quote } from "./types";

type Props = {
  guide: GuidedState;
  quote: Quote | null;
  expired: boolean;
  busy: boolean;
  locale: Locale;
  onAction: (action: GuidedAction) => void;
  onStart: (scenario: GuidedScenario) => void;
  onExit: () => void;
};

export function GuidedPanel({ guide, quote, expired, busy, locale, onAction, onStart, onExit }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  const { stage, view } = guide;
  useEffect(() => {
    heading.current?.focus();
  }, [view.session.id, stage]);

  return localizeTree(
    <aside className="voice-panel guided-panel" aria-labelledby="guided-heading">
      <div className="panel-heading">
        <span className="eyebrow">AMB GUIÓ</span>
        <button className="text-button" onClick={onExit} disabled={busy}>Sortir</button>
      </div>
      <h2 id="guided-heading" tabIndex={-1} ref={heading}>Demostració guiada</h2>
      <p className="small-note">Segueix una conversa preparada. L’estoc i la reserva es calculen al servidor.</p>

      {stage !== "outage" && (
        <blockquote data-untranslated lang="en">
          I need a navy shirt for a wedding. Size M, under €120.
        </blockquote>
      )}
      {stage !== "outage" && stage !== "initial" && (
        <blockquote data-untranslated lang="es">Espera, mejor en verde salvia.</blockquote>
      )}

      {expired ? (
        <p role="status">La demostració ha caducat. Torna a començar.</p>
      ) : (
        <div className="guided-actions">
          {stage === "initial" && (
            <button className="primary" disabled={busy} onClick={() => onAction("change-colour")}>
              Canviar a verd salvia en castellà
            </button>
          )}
          {stage === "revised" && (
            <button className="primary" disabled={busy} onClick={() => onAction("check")}>
              Comprovar talla i enviament
            </button>
          )}
          {stage === "quoted" && (quote ? (
            <>
              <dl className="guided-quote">
                <dt>Peça</dt>
                <dd>{view.products[0]?.name} · M · <span>sage</span></dd>
                <dt>Preu de la peça</dt><dd>{euro(quote.item_price_cents, locale)}</dd>
                <dt>Enviament</dt><dd>{euro(quote.shipping_cents, locale)}</dd>
                <dt>Destinació</dt><dd>{quote.destination}</dd>
                <dt>Límit demanat</dt><dd>{date(quote.requested_date, locale)}</dd>
              </dl>
              <button className="primary" disabled={busy} onClick={() => onAction("reserve")}>
                Confirmar la reserva de 10 minuts
              </button>
              <button className="secondary" disabled={busy} onClick={() => onAction("decline")}>
                No reservar
              </button>
            </>
          ) : (
            <button className="primary" disabled={busy} onClick={() => onAction("check")}>
              Actualitzar l’estimació
            </button>
          ))}
          {stage === "held" && <p role="status">La botiga ha creat una reserva sintètica.</p>}
          {stage === "declined" && <p role="status">La botiga no ha creat cap reserva.</p>}
          {stage === "outage" && <p role="status">La botiga no pot confirmar l’estoc.</p>}
        </div>
      )}

      <div className="guided-alternatives">
        {stage !== "outage" && (
          <button className="text-button" disabled={busy} onClick={() => onStart("inventory-outage")}>
            Provar una fallada d’inventari
          </button>
        )}
        <button className="text-button" disabled={busy} onClick={() => onStart("normal")}>
          Tornar a començar
        </button>
      </div>
    </aside>,
    locale,
  );
}
