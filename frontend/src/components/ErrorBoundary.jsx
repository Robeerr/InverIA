import React from "react";

// Red de seguridad: si cualquier componente lanza una excepción al renderizar, en vez de
// dejar la PANTALLA EN BLANCO (especialmente en el iPhone), mostramos un mensaje amable con
// un botón para reintentar. Los Error Boundaries de React deben ser componentes de clase.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Log en consola para depurar; no rompemos la app.
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary capturó un error de render:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="max-w-md mx-auto mt-20 px-6 text-center">
          <p className="text-4xl mb-3">😵‍💫</p>
          <h2 className="font-heading font-bold text-lg text-[#0e1f1a] mb-2">Algo se ha roto en esta vista</h2>
          <p className="text-sm text-[#5c6b66] mb-5">
            No te preocupes, tus datos están a salvo. Prueba a recargar o volver a la pantalla principal.
          </p>
          <div className="flex gap-2 justify-center">
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-md bg-[#1a3a32] text-white text-sm font-mono hover:bg-[#0e1f1a] transition-colors"
            >
              Recargar
            </button>
            <button
              onClick={() => { this.handleReset(); window.location.href = "/"; }}
              className="px-4 py-2 rounded-md border border-[#e5e0d8] text-[#5c6b66] text-sm font-mono hover:border-[#1a3a32] transition-colors"
            >
              Ir al inicio
            </button>
          </div>
          {/* El detalle técnico, plegado. Esta pantalla salió varias veces sin decir NUNCA
              qué se había roto: había que pedir la consola del navegador para saberlo, y
              desde el móvil eso no es viable. El mensaje de una excepción suele señalar la
              línea culpable directamente. Va plegado para no asustar a quien solo quiere
              recargar, y seleccionable para poder copiarlo y pegarlo. */}
          {this.state.error && (
            <details className="mt-6 text-left">
              <summary className="text-[11px] font-mono text-[#5c6b66] cursor-pointer select-none">
                Detalle técnico
              </summary>
              <pre className="mt-2 p-3 rounded-md bg-[#f0ece3] text-[#0e1f1a] text-[10px] font-mono whitespace-pre-wrap break-words select-all max-h-48 overflow-auto">
                {String(this.state.error?.message || this.state.error)}
              </pre>
            </details>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
