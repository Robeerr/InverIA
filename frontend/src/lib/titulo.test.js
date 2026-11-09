import { tituloDePagina } from "./titulo";

describe("tituloDePagina · el nombre de la pestaña", () => {
  it("la portada ya no se llama «AAPL · InverIA»", () => {
    expect(tituloDePagina("/")).toBe("Hoy · InverIA");
  });

  it("la ficha de una acción lleva su ticker", () => {
    expect(tituloDePagina("/accion/orcl")).toBe("ORCL · InverIA");
  });

  it("cada pantalla lleva su nombre", () => {
    expect(tituloDePagina("/cartera")).toBe("Cartera · InverIA");
    expect(tituloDePagina("/operaciones")).toBe("Operaciones · InverIA");
    expect(tituloDePagina("/track-record")).toBe("Track record · InverIA");
    expect(tituloDePagina("/sistema/estilos")).toBe("Estilos · InverIA");
  });

  it("un enlace mal codificado no rompe la app", () => {
    expect(tituloDePagina("/accion/%")).toBe("% · InverIA");
  });

  it("una ruta desconocida no se hace pasar por otra pantalla", () => {
    expect(tituloDePagina("/no-existe")).toBe("InverIA");
  });
});
