/**
 * Lo que el Track record le dice al usuario, en palabras.
 *
 * Batir al índice y ganar dinero son dos cosas distintas. Si el mercado cae un 2,5 % y el
 * motor un 0,7 %, el motor «bate» al índice, pero quien lo siguió ha perdido dinero. La
 * pantalla lo presentaba como «aporta valor sobre comprar SPY y esperar»; esto separa los
 * cuatro casos y elige el color con los dos criterios a la vez.
 */

const signo = (x) => `${x > 0 ? "+" : ""}${x}%`;
const red1 = (x) => Math.round(x * 10) / 10;

/** Veredicto a partir de las cifras, para respuestas antiguas del servidor que no lo traen. */
function veredictoDe(b) {
  const gana = b.sistema_medio > 0;
  const bate = b.sistema_medio > b.spy_medio;
  if (gana && bate) return "gana_y_bate";
  if (gana) return "gana_sin_batir";
  if (bate) return "pierde_menos_que_indice";
  return "pierde_y_no_bate";
}

/** Texto, tono (sube/aviso/baja) y nota de método del bloque «¿Bate al índice?». */
export function lecturaBenchmark(b) {
  const v = b.veredicto || veredictoDe(b);
  const dif = red1(Math.abs(b.sistema_medio - b.spy_medio));
  const textos = {
    gana_y_bate: `Tu motor gana un ${signo(b.sistema_medio)} de media por señal y bate al índice por ${dif} puntos. El ${b.baten_spy_pct}% de las señales lo superan.`,
    gana_sin_batir: `Tu motor gana un ${signo(b.sistema_medio)} de media, pero comprar el índice y esperar habría dado un ${signo(b.spy_medio)}: rinde ${dif} puntos menos.`,
    pierde_menos_que_indice: `Tu motor pierde un ${Math.abs(b.sistema_medio)}% de media por señal. El índice cayó más (${signo(b.spy_medio)}) en las mismas fechas, pero perder menos que el mercado no es ganar dinero.`,
    pierde_y_no_bate: `Tu motor pierde un ${Math.abs(b.sistema_medio)}% de media por señal y rinde ${dif} puntos menos que comprar el índice y esperar.`,
  };
  const tonos = { gana_y_bate: "sube", gana_sin_batir: "aviso",
    pierde_menos_que_indice: "aviso", pierde_y_no_bate: "baja" };
  return {
    texto: textos[v],
    tono: tonos[v],
    metodo: `Cada señal se compara con el S&P 500 en su misma ventana (de su fecha a su cierre, o a hoy si sigue abierta) y con los mismos costes (${b.muestra} señales).`,
  };
}

/** La línea que dice qué se ha descontado y qué se ha quitado, o null si no hay datos. */
export function notaCostes(costes, duplicadas) {
  if (!costes || costes.pct_ida_vuelta == null) return null;
  let t = `Retornos netos: descontado un ${costes.pct_ida_vuelta}% por operación (comisiones de DEGIRO y cambio de divisa, al comprar y al vender, en una operación de ${costes.importe_referencia_eur} €).`;
  if (duplicadas > 0) {
    t += ` Se han descartado ${duplicadas} señales duplicadas (el mismo análisis regenerado el mismo día).`;
  }
  return t;
}
