import {
  Children,
  cloneElement,
  isValidElement,
  type ReactNode,
  type ReactElement,
} from "react";
export type Locale = "en" | "ca" | "es";
export const localeCode: Record<Locale, string> = {
  en: "en-GB",
  ca: "ca-ES",
  es: "es-ES",
};
// Exact source text is the key. Unknown catalogue text stays original rather than acquiring invented facts.
const sourceRows = `
Idioma de la interfície|Interface language|Idioma de la interfaz
La llengua de la web no canvia la veu de la conversa.|The site language does not change the language of an ongoing voice call.|El idioma de la web no cambia el de una conversación de voz en curso.
Fil inici|Fil home|Fil inicio
Provar la demostració guiada|Try the guided demo|Probar la demostración guiada
Anar a la veu en directe|Go to live voice|Ir a la voz en directo
AMB GUIÓ|SCRIPTED|CON GUIÓN
Demostració guiada|Guided demo|Demostración guiada
Sortir|Exit|Salir
Segueix una conversa preparada. L’estoc i la reserva es calculen al servidor.|Follow a scripted conversation. The shop server calculates stock and creates the hold.|Sigue una conversación preparada. El servidor calcula las existencias y crea la reserva.
La demostració ha caducat. Torna a començar.|The demo has expired. Start over.|La demostración ha caducado. Vuelve a empezar.
Canviar a verd salvia en castellà|Switch to Spanish and ask for sage|Cambiar a español y pedir verde salvia
Comprovar talla i enviament|Check size and delivery|Comprobar talla y envío
Peça|Item|Prenda
Preu de la peça|Item price|Precio de la prenda
Enviament|Shipping|Envío
Límit demanat|Requested deadline|Fecha límite solicitada
Confirmar la reserva de 10 minuts|Confirm the 10-minute hold|Confirmar la reserva de 10 minutos
No reservar|Decline the hold|Rechazar la reserva
Actualitzar l’estimació|Refresh delivery estimate|Actualizar la estimación de entrega
La botiga ha creat una reserva sintètica.|The shop created a synthetic hold.|La tienda ha creado una reserva simulada.
La botiga no ha creat cap reserva.|The shop created no hold.|La tienda no ha creado ninguna reserva.
La botiga no pot confirmar l’estoc.|The shop cannot confirm stock.|La tienda no puede confirmar las existencias.
Provar una fallada d’inventari|Try an inventory outage|Probar un fallo de inventario
Tornar a començar|Start over|Volver a empezar
Reserva rebutjada|Hold declined|Reserva rechazada
PECES AMB CALMA.|THOUGHTFUL PIECES.|PRENDAS CON CALMA.
CONVERSES AMB SENTIT.|MEANINGFUL CONVERSATIONS.|CONVERSACIONES CON SENTIDO.
BOTIGA FICTÍCIA · DEMOSTRACIÓ|FICTIONAL SHOP · DEMO|TIENDA FICTICIA · DEMOSTRACIÓN
Tancar|Close|Cerrar
Veure|View|Ver
les accions|activity|las acciones
EL TEU ESTIL COMENÇA AMB UNA CONVERSA|YOUR STYLE STARTS WITH A CONVERSATION|TU ESTILO EMPIEZA CON UNA CONVERSACIÓN
Troba allò|Find something|Encuentra algo
que va|that feels|que vaya
amb tu.|like you.|contigo.
Un casament, un color, una idea a mig fer.|A wedding, a colour, a half-formed idea.|Una boda, un color, una idea a medias.
Explica-ho a l’Ona. En trobarem el fil.|Tell Ona. We’ll find the thread.|Cuéntaselo a Ona. Encontraremos el hilo.
Un fil dibuixa un llaç|A thread draws a loop|Un hilo dibuja un lazo
Menys buscar.|Less searching.|Menos buscar.
Més trobar-te.|More finding yourself.|Más encontrarte.
01 — UNA PETITA SELECCIÓ, PER A TU|01 — A SMALL SELECTION, JUST FOR YOU|01 — UNA PEQUEÑA SELECCIÓN, PARA TI
Tancar ×|Close ×|Cerrar ×
Preparant la botiga…|Getting the shop ready…|Preparando la tienda…
Tornar a carregar|Reload|Volver a cargar
UNA INVITACIÓ A PROVAR-HO|AN INVITATION TO TRY|UNA INVITACIÓN A PROBAR
Benvingut a Fil.|Welcome to Fil.|Bienvenido a Fil.
Introdueix el codi d’accés a la demostració.|Enter your demo access code.|Introduce el código de acceso a la demostración.
Codi d’accés|Access code|Código de acceso
Entrar|Enter|Entrar
Conversa amb l’Ona|Conversation with Ona|Conversación con Ona
LA TEVA ASSISTENT|YOUR ASSISTANT|TU ASISTENTE
Cancel·lant…|Cancelling…|Cancelando…
Connectant…|Connecting…|Conectando…
Micro silenciat|Microphone muted|Micrófono silenciado
L’Ona parla|Ona is speaking|Ona está hablando
L’Ona t’escolta|Ona is listening|Ona te escucha
Coneix l’Ona|Meet Ona|Conoce a Ona
Parla, interromp, canvia d’idea. L’Ona segueix el teu ritme.|Speak, interrupt, change your mind. Ona follows your lead.|Habla, interrumpe, cambia de idea. Ona sigue tu ritmo.
Una assistent d’IA que t’ajuda a triar. Sense compte, sense presses.|An AI assistant to help you choose. No account, no rush.|Una asistente de IA que te ayuda a elegir. Sin cuenta, sin prisas.
Parlar amb l’Ona|Talk to Ona|Hablar con Ona
Activar micro|Unmute|Activar micro
Silenciar|Mute|Silenciar
Acabar|End call|Terminar
Tancar la sessió anterior|Close the previous session|Cerrar la sesión anterior
El servei de veu encara no està configurat.|The voice service is not configured yet.|El servicio de voz aún no está configurado.
Micro|Microphone|Micro
Veu|Voice|Voz
Senyal d’àudio rebut|Audio signal received|Señal de audio recibida
Esperant senyal d’àudio|Waiting for audio|Esperando señal de audio
Un moment per al so|A moment for sound|Un momento para el sonido
Esperant permís · cancel·lar|Waiting for permission · cancel|Esperando permiso · cancelar
Digues alguna cosa…|Say something…|Di algo…
Micròfon autoritzat|Microphone allowed|Micrófono autorizado
Provar micròfon|Test microphone|Probar micrófono
Permet l’accés al navegador|Allow access in your browser|Permite el acceso en el navegador
Nivell d’entrada|Input level|Nivel de entrada
Provar altaveu|Test speaker|Probar altavoz
Escolta un to breu|Listen for a short tone|Escucha un tono breve
He sentit el to|I heard the tone|He oído el tono
Volum|Volume|Volumen
Opcions de demostració|Demo options|Opciones de demostración
Situació|Scenario|Situación
Compra amb Ona|Shopping with Ona|Compra con Ona
Inventari no disponible|Inventory unavailable|Inventario no disponible
El catàleg, l’estoc i els enviaments són sintètics. No hi ha compres ni cobrament.|Catalogue, stock and delivery are synthetic. No purchases or payments.|El catálogo, el stock y los envíos son sintéticos. No hay compras ni cobros.
TRIAT A PARTIR DEL QUE ENS EXPLIQUES|CHOSEN FROM WHAT YOU TELL US|ELEGIDO A PARTIR DE LO QUE NOS CUENTAS
La teva selecció|Your selection|Tu selección
peces|pieces|prendas
No podem confirmar la selecció actual.|We can’t confirm the current selection.|No podemos confirmar la selección actual.
La sessió ha caducat. Comença una conversa nova per consultar l’estoc actual.|Your session has expired. Start a new conversation to check current stock.|La sesión ha caducado. Inicia una conversación nueva para consultar el stock actual.
La consulta no s’ha completat. L’Ona pot ajudar-te a tornar-ho a provar; no mostrem disponibilitat anterior.|The check didn’t complete. Ona can help you try again; previous availability is hidden.|La consulta no se ha completado. Ona puede ayudarte a intentarlo de nuevo; no mostramos disponibilidad anterior.
SELECCIÓ ACTUAL|CURRENT SELECTION|SELECCIÓN ACTUAL
Talla|Size|Talla
Fins a|Up to|Hasta
/ peça|/ item|/ prenda
IL·LUSTRACIÓ · COLOR ORIENTATIU|ILLUSTRATION · COLOUR GUIDE ONLY|ILUSTRACIÓN · COLOR ORIENTATIVO
Sense estoc|Out of stock|Sin stock
Estoc no confirmat|Stock unconfirmed|Stock sin confirmar
— no confirmat|— unconfirmed|— sin confirmar
— esgotat|— sold out|— agotado
Com és i com queda|Details and fit|Detalles y ajuste
Pit|Chest|Pecho
cm · llarg|cm · length|cm · largo
Mesures de la peça, no una garantia de talla.|Garment measurements, not a fit guarantee.|Medidas de la prenda, no una garantía de talla.
Estoc segons l’última consulta. Preu per peça. Enviament a part. Demana a l’Ona que comprovi la talla i el color exactes.|Stock from the latest check. Price per item; shipping extra. Ask Ona to check the exact size and colour.|Stock de la última consulta. Precio por prenda; envío aparte. Pide a Ona que compruebe la talla y el color exactos.
Encara no hem trobat la peça.|We haven’t found your piece yet.|Aún no hemos encontrado tu prenda.
Comencem per una idea.|Let’s start with an idea.|Empecemos por una idea.
No hi ha coincidències amb aquests criteris. Pots parlar amb l’Ona abans de canviar-los.|Nothing matches these criteria. Talk to Ona before changing them.|No hay coincidencias con estos criterios. Habla con Ona antes de cambiarlos.
Les peces apareixeran aquí quan l’Ona consulti el catàleg per a tu.|Pieces will appear here when Ona searches the catalogue for you.|Las prendas aparecerán aquí cuando Ona consulte el catálogo para ti.
“Tinc un casament, però no vull anar|“I’m going to a wedding, but don’t want to look|“Tengo una boda, pero no quiero ir
massa formal. Què em recomanes?”|too formal. What would you suggest?”|demasiado formal. ¿Qué me recomiendas?”
CAP PEÇA SELECCIONADA ENCARA|NO PIECES SELECTED YET|NINGUNA PRENDA SELECCIONADA AÚN
UNA COMPROVACIÓ CONCRETA|AN EXACT VARIANT CHECK|UNA COMPROBACIÓN CONCRETA
Variant consultada|Checked variant|Variante consultada
Arribada estimada:|Estimated arrival:|Llegada estimada:
No confirmada|Unconfirmed|Sin confirmar
Enviament:|Shipping:|Envío:
Exprés|Express|Exprés
Estàndard|Standard|Estándar
Peça:|Item:|Prenda:
· total amb enviament:|· total including shipping:|· total con envío:
Estimació sintètica · vàlida|Synthetic estimate · valid for|Estimación sintética · válida durante
No hi ha cap proposta de reserva vigent. Consulta amb l’Ona la destinació i la data.|No current reservation quote. Check the destination and date with Ona.|No hay una propuesta de reserva vigente. Consulta con Ona el destino y la fecha.
El fil de la conversa|The conversation thread|El hilo de la conversación
ONA + TU|ONA + YOU|ONA + TÚ
Transcripció de la conversa|Conversation transcript|Transcripción de la conversación
Aquí quedarà el que us aneu dient.|Your conversation will appear here.|Aquí aparecerá vuestra conversación.
TU|YOU|TÚ
VISTA DE L’OPERADOR|OPERATOR VIEW|VISTA DEL OPERADOR
Allò que ha passat, de debò.|What actually happened.|Lo que ha pasado, de verdad.
Resultats reals dels serveis de demostració. Historial separat de la selecció actual; sense raonament intern ni credencials.|Actual demo service results. History is separate from the current selection; no internal reasoning or credentials.|Resultados reales de los servicios de demostración. Historial separado de la selección actual; sin razonamiento interno ni credenciales.
Encara no hi ha accions.|No activity yet.|Aún no hay acciones.
Cerca de peces|Product search|Búsqueda de prendas
Comprovació de variant|Variant check|Comprobación de variante
Reserva d’una peça|Item reservation|Reserva de una prenda
Reintent de l’operador|Operator retry|Reintento del operador
Acció del servei|Service action|Acción del servicio
No completada|Not completed|No completada
Completada|Completed|Completada
RESERVA OBSERVADA|OBSERVED RESERVATION|RESERVA OBSERVADA
Retenció activa|Active hold|Retención activa
Retenció caducada|Expired hold|Retención caducada
Repetint…|Retrying…|Reintentando…
Provar reintent de la reserva|Test reservation retry|Probar reintento de la reserva
Nova reserva retornada|New reservation returned|Nueva reserva devuelta
Mateixa reserva · created: false|Same reservation · created: false|Misma reserva · created: false
El reintent només apareix després d’una reserva existent. Mai en crea la primera.|Retry is available only after a reservation exists. It never creates the first one.|El reintento solo aparece después de una reserva existente. Nunca crea la primera.
Roba fictícia. Converses amb sentit.|Fictional clothes. Meaningful conversations.|Ropa ficticia. Conversaciones con sentido.
Una demostració de Jordi Catafal ↗|A demo by Jordi Catafal ↗|Una demostración de Jordi Catafal ↗
UNA PEÇA, GUARDADA PER A TU|ONE PIECE, HELD FOR YOU|UNA PRENDA, GUARDADA PARA TI
RESERVA FINALITZADA|RESERVATION ENDED|RESERVA FINALIZADA
La teva reserva està feta.|Your piece is reserved.|Tu reserva está hecha.
El temps de reserva ha acabat.|Your reservation has expired.|El tiempo de reserva ha terminado.
Peça|Item|Prenda
+ enviament|+ shipping|+ envío
Reserva de demostració, no una compra.|Demo reservation, not a purchase.|Reserva de demostración, no una compra.
MINUTS RESTANTS|MINUTES LEFT|MINUTOS RESTANTES
SENSE RETENCIÓ ACTIVA|NO ACTIVE HOLD|SIN RETENCIÓN ACTIVA
Microfon del navegador|Browser microphone|Micrófono del navegador
Micròfon del navegador|Browser microphone|Micrófono del navegador
Connectat. Comprova que sents l’Ona; la connexió no confirma que l’àudio sigui audible.|Connected. Check you can hear Ona; a connection does not confirm audible audio.|Conectado. Comprueba que oyes a Ona; la conexión no confirma que el audio sea audible.
No s’ha pogut mantenir la conversa de veu. Revisa el micròfon i la sortida d’àudio, tanca la sessió i torna-ho a provar.|The voice connection failed. Check your microphone and audio output, close the session and try again.|No se ha podido mantener la conversación de voz. Revisa el micrófono y la salida de audio, cierra la sesión e inténtalo de nuevo.
Si no sents l’Ona, comprova el volum i la sortida del navegador. Pots tornar a provar l’altaveu; si cal, acaba la trucada i reconnecta.|If you can’t hear Ona, check your volume and browser audio output. Test the speaker again; if needed, end the call and reconnect.|Si no oyes a Ona, comprueba el volumen y la salida del navegador. Prueba de nuevo el altavoz; si hace falta, termina la llamada y vuelve a conectar.
Encara no hem rebut permís de micròfon. Revisa l’avís del navegador i torna-ho a provar; la prova ha deixat d’esperar.|Microphone permission is still pending. Check the browser prompt and try again; this test has stopped waiting.|Aún no hemos recibido permiso de micrófono. Revisa el aviso del navegador e inténtalo de nuevo; la prueba ha dejado de esperar.
No podem accedir al micròfon. Permet-ne l’accés a la barra d’adreces, revisa el dispositiu i torna a provar-lo. Cal HTTPS o localhost.|We can’t access the microphone. Allow it in the address bar, check the device and test again. HTTPS or localhost is required.|No podemos acceder al micrófono. Permite el acceso en la barra de direcciones, revisa el dispositivo y prueba de nuevo. Se necesita HTTPS o localhost.
El navegador ha bloquejat la sortida d’àudio. Activa el so d’aquesta pestanya i torna a prémer «Provar altaveu».|Your browser blocked audio output. Enable sound for this tab and select “Test speaker” again.|El navegador ha bloqueado la salida de audio. Activa el sonido de esta pestaña y pulsa «Probar altavoz» otra vez.
La connexió ha trigat massa. Tanca la sessió i torna-ho a provar.|The connection timed out. Close the session and try again.|La conexión ha tardado demasiado. Cierra la sesión e inténtalo de nuevo.
Cancel·lant la connexió pendent…|Cancelling the pending connection…|Cancelando la conexión pendiente…
Introdueix el codi d’accés per obrir la demostració.|Enter the access code to open the demo.|Introduce el código de acceso para abrir la demostración.
Aquest origen no està autoritzat. Obre l’adreça configurada per a la demostració.|This origin is not authorised. Open the configured demo address.|Este origen no está autorizado. Abre la dirección configurada para la demostración.
Aquesta demostració només està disponible des de l’ordinador local.|This demo is only available on the local computer.|Esta demostración solo está disponible desde el ordenador local.
Ja hi ha una sessió oberta. Tanca-la abans de començar-ne una altra.|A session is already open. Close it before starting another.|Ya hay una sesión abierta. Ciérrala antes de empezar otra.
Hem arribat al límit d’intents. Espera uns minuts abans de tornar-ho a provar.|The attempt limit has been reached. Wait a few minutes before trying again.|Se ha alcanzado el límite de intentos. Espera unos minutos antes de volver a probar.
La sessió ha caducat. Tanca-la i inicia una conversa nova.|The session has expired. Close it and start a new conversation.|La sesión ha caducado. Ciérrala e inicia una conversación nueva.
No podem connectar amb el servei de veu. Torna-ho a provar més tard.|We can’t connect to the voice service. Try again later.|No podemos conectar con el servicio de voz. Inténtalo más tarde.
No hi ha cap reserva vigent que es pugui repetir.|There is no active reservation to retry.|No hay ninguna reserva vigente que se pueda reintentar.
L’inventari no està disponible ara. No podem confirmar cap peça ni reserva.|Inventory is unavailable right now. We can’t confirm any item or reservation.|El inventario no está disponible ahora. No podemos confirmar ninguna prenda ni reserva.
L’estimació ha caducat. Demana a l’Ona que comprovi de nou la variant i l’enviament.|The quote has expired. Ask Ona to check the variant and delivery again.|La propuesta ha caducado. Pide a Ona que compruebe otra vez la variante y el envío.
La reserva ha caducat. Un reintent no crea cap reserva nova.|The reservation has expired. A retry does not create a new hold.|La reserva ha caducado. Un reintento no crea una reserva nueva.
El codi d’accés no és correcte.|The access code is incorrect.|El código de acceso no es correcto.
No hem pogut completar l’acció. Torna-ho a provar.|We couldn’t complete the action. Please try again.|No hemos podido completar la acción. Inténtalo de nuevo.
No hi ha connexió amb la demostració. Comprova el servei i torna-ho a provar.|The demo is unreachable. Check the service and try again.|No hay conexión con la demostración. Comprueba el servicio e inténtalo de nuevo.
Camisa Brisa|Brisa Shirt|Camisa Brisa
Camisa Riu|Riu Shirt|Camisa Riu
Camisa Nit|Nit Shirt|Camisa Nit
Top Alba|Alba Top|Top Alba
Top Ona|Ona Top|Top Ona
Jaqueta Mar|Mar Jacket|Chaqueta Mar
Jaqueta Terra|Terra Jacket|Chaqueta Terra
Jaqueta Núvol|Núvol Jacket|Chaqueta Núvol
Camisa lleugera de lli i cotó.|Lightweight linen and cotton shirt.|Camisa ligera de lino y algodón.
Camisa de lli amb coll obert.|Linen shirt with an open collar.|Camisa de lino con cuello abierto.
Camisa de popelín de cotó.|Cotton poplin shirt.|Camisa de popelín de algodón.
Top fluid de viscosa amb màniga curta.|Fluid viscose top with short sleeves.|Top fluido de viscosa con manga corta.
Top recte de lyocell amb coll rodó.|Straight-cut lyocell top with a round neck.|Top recto de lyocell con cuello redondo.
Jaqueta de lli sense estructura rígida.|Unstructured linen jacket.|Chaqueta de lino sin estructura rígida.
Jaqueta lleugera de cotó amb butxaques.|Lightweight cotton jacket with pockets.|Chaqueta ligera de algodón con bolsillos.
Jaqueta curta de cotó suau.|Cropped jacket in soft cotton.|Chaqueta corta de algodón suave.
Tall recte. Compara el contorn de pit de la peça amb una camisa que et vagi bé.|Straight cut. Compare the garment’s chest circumference with a shirt that fits you well.|Corte recto. Compara el contorno de pecho de la prenda con una camisa que te quede bien.
Tall ample i espatlla relaxada; la talla habitual és només un punt de partida.|Loose cut and relaxed shoulders; your usual size is only a starting point.|Corte amplio y hombro relajado; tu talla habitual es solo un punto de partida.
Tall entallat. Si prefereixes folgança, contrasta la mida de pit de la peça.|Tailored cut. If you prefer more room, check the garment’s chest measurement.|Corte entallado. Si prefieres holgura, contrasta la medida de pecho de la prenda.
Caiguda fluida, sense ajustar la cintura. Consulta llargada i contorn de pit.|Fluid drape without a fitted waist. Check length and chest circumference.|Caída fluida, sin ajustar la cintura. Consulta el largo y el contorno de pecho.
Tall recte; compara les mides de la peça amb un top propi, sense assumir ajust.|Straight cut; compare the garment measurements with a top you own, without assuming fit.|Corte recto; compara las medidas de la prenda con un top propio, sin asumir el ajuste.
Tall relaxat per portar sobre una camisa; comprova l'espai de pit amb la capa inferior.|Relaxed cut for wearing over a shirt; check chest room with the layer underneath.|Corte relajado para llevar sobre una camisa; comprueba el espacio de pecho con la capa inferior.
Tall recte; la llargada és de la peça, no una recomanació basada en l'alçada.|Straight cut; length is the garment measurement, not a recommendation based on height.|Corte recto; el largo es el de la prenda, no una recomendación basada en la altura.
Tall curt i ample; consulta la llargada abans de triar la talla.|Short, loose cut; check the length before choosing a size.|Corte corto y amplio; consulta el largo antes de elegir la talla.
`;
const dictionary: Record<string, { en: string; ca: string; es: string }> = {};
for (const row of sourceRows.trim().split("\n")) {
  const [ca, en, es] = row.split("|");
  dictionary[ca] = { ca, en, es };
}
const colours: Record<string, Record<Locale, string>> = {
  ivory: { en: "Ivory", ca: "Ivori", es: "Marfil" },
  navy: { en: "Navy", ca: "Blau marí", es: "Azul marino" },
  sage: { en: "Sage", ca: "Verd sàlvia", es: "Verde salvia" },
  black: { en: "Black", ca: "Negre", es: "Negro" },
  terracotta: { en: "Terracotta", ca: "Terracota", es: "Terracota" },
};
export function translate(source: string, locale: Locale): string {
  const key = source.replace(/\s+/g, " ").trim();
  let value = dictionary[key]?.[locale] ?? colours[key]?.[locale];
  if (value === undefined) {
    const stock = key.match(/^(\d+) disponibles$/);
    if (stock)
      value =
        locale === "en"
          ? `${stock[1]} available`
          : locale === "es"
            ? `${stock[1]} disponibles`
            : key;
    const variant = key.match(/^(.+) · talla (S|M|L)$/);
    if (variant)
      value = `${translate(variant[1], locale)} · ${locale === "en" ? "size" : "talla"} ${variant[2]}`;
    const alt = key.match(/^Il·lustració neutra de (.+)$/);
    if (alt)
      value = `${locale === "en" ? "Neutral illustration of" : locale === "es" ? "Ilustración neutra de" : "Il·lustració neutra de"} ${translate(alt[1], locale)}`;
    if (value === undefined && key.includes(" · "))
      value = key
        .split(" · ")
        .map((part) => translate(part, locale))
        .join(" · ");
  }
  if (value === undefined) return source;
  return (
    (source.match(/^\s*/)?.[0] ?? "") +
    value +
    (source.match(/\s*$/)?.[0] ?? "")
  );
}
// Translate presentation only. Handlers, IDs, numeric data and the spoken transcript stay untouched.
export function localizeTree(node: ReactNode, locale: Locale): ReactNode {
  if (typeof node === "string") return translate(node, locale);
  if (Array.isArray(node))
    return Children.map(node, (child) => localizeTree(child, locale));
  if (!isValidElement(node)) return node;
  const element = node as ReactElement<Record<string, unknown>>;
  if (element.props["data-untranslated"] || element.type === "code")
    return node;
  const props: Record<string, unknown> = {};
  for (const key of ["aria-label", "alt", "title", "placeholder", "label"])
    if (typeof element.props[key] === "string")
      props[key] = translate(element.props[key] as string, locale);
  if ("children" in element.props)
    props.children = localizeTree(element.props.children as ReactNode, locale);
  return cloneElement(element, props);
}
export const metadata: Record<Locale, { title: string; description: string }> =
  {
    en: {
      title: "Fil — Find your thread.",
      description:
        "Fil is a fictional clothing boutique. Find your piece by talking with Ona. Synthetic catalogue and reservations.",
    },
    ca: {
      title: "Fil — Troba el teu fil.",
      description:
        "Fil: una petita botiga de roba fictícia. Troba la teva peça parlant amb l’Ona. Catàleg i reserves de demostració.",
    },
    es: {
      title: "Fil — Encuentra tu hilo.",
      description:
        "Fil: una pequeña tienda de ropa ficticia. Encuentra tu prenda hablando con Ona. Catálogo y reservas de demostración.",
    },
  };
