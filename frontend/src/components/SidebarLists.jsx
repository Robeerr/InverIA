import React from "react";
import { Star, Trash, ArrowUpRight, ArrowDownRight, Plus, BellRinging, X } from "@phosphor-icons/react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { fmtPrice, fmtPct } from "../lib/format";

export default function SidebarLists({
  watchlist,
  onPickSymbol,
  onRemoveSymbol,
  onAddCurrent,
  currentSymbol,
  alerts,
  onAddAlert,
  onRemoveAlert,
  popular,
}) {
  return (
    <aside data-testid="sidebar" className="card-flat p-4">
      <Tabs defaultValue="watchlist">
        <TabsList className="bg-[#f5f3ef] border border-[#e5e0d8] grid grid-cols-3 mb-4">
          <TabsTrigger value="watchlist" data-testid="tab-watchlist">Watchlist</TabsTrigger>
          <TabsTrigger value="alerts" data-testid="tab-alerts">Alertas</TabsTrigger>
          <TabsTrigger value="popular" data-testid="tab-popular">Populares</TabsTrigger>
        </TabsList>

        <TabsContent value="watchlist">
          <Button
            data-testid="add-current-watchlist"
            onClick={onAddCurrent}
            disabled={!currentSymbol}
            className="w-full mb-3 bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono text-xs"
          >
            <Plus size={14} weight="bold" className="mr-1" />
            Añadir {currentSymbol || "—"}
          </Button>
          <div className="space-y-1 max-h-[420px] overflow-y-auto">
            {(watchlist || []).length === 0 && (
              <p className="text-xs text-[#5c6b66] text-center py-6">Tu watchlist está vacía.</p>
            )}
            {(watchlist || []).map((item) => {
              const q = item.quote;
              const up = (q?.change ?? 0) >= 0;
              return (
                <div
                  key={item.id}
                  data-testid={`watchlist-item-${item.symbol}`}
                  className="group flex items-center gap-2 p-2 hover:bg-[#f5f3ef] rounded-md cursor-pointer transition-colors"
                  onClick={() => onPickSymbol(item.symbol)}
                >
                  <Star size={14} weight="fill" className="text-[#1a3a32] shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="font-mono font-semibold text-sm text-[#0e1f1a]">{item.symbol}</p>
                    <p className="text-[10px] text-[#5c6b66] truncate">{q?.name || ""}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-mono text-xs text-[#0e1f1a]">${fmtPrice(q?.price)}</p>
                    <p className={`font-mono text-[10px] ${up ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                      {fmtPct(q?.change_percent)}
                    </p>
                  </div>
                  <button
                    data-testid={`remove-watchlist-${item.symbol}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemoveSymbol(item.symbol);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-[#5c6b66] hover:text-[#d85c41] transition-opacity"
                  >
                    <Trash size={14} />
                  </button>
                </div>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="alerts">
          <AlertForm currentSymbol={currentSymbol} onSubmit={onAddAlert} />
          <div className="space-y-2 mt-3 max-h-[400px] overflow-y-auto">
            {(alerts || []).length === 0 && (
              <p className="text-xs text-[#5c6b66] text-center py-4">No tienes alertas.</p>
            )}
            {(alerts || []).map((a) => (
              <div key={a.id} data-testid={`alert-${a.id}`} className="flex items-center gap-2 p-2 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
                <BellRinging size={14} weight="bold" className="text-[#1a3a32]" />
                <div className="flex-1">
                  <p className="font-mono text-xs font-semibold text-[#0e1f1a]">
                    {a.symbol} {a.direction === "above" ? "≥" : "≤"} ${fmtPrice(a.target_price)}
                  </p>
                </div>
                <button
                  data-testid={`remove-alert-${a.id}`}
                  onClick={() => onRemoveAlert(a.id)}
                  className="text-[#5c6b66] hover:text-[#d85c41]"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="popular">
          <div className="space-y-1 max-h-[440px] overflow-y-auto">
            {(popular || []).map((q) => {
              const up = (q?.change ?? 0) >= 0;
              const TrendIcon = up ? ArrowUpRight : ArrowDownRight;
              return (
                <div
                  key={q.symbol}
                  data-testid={`popular-${q.symbol}`}
                  className="flex items-center gap-2 p-2 hover:bg-[#f5f3ef] rounded-md cursor-pointer transition-colors"
                  onClick={() => onPickSymbol(q.symbol)}
                >
                  <div className="w-8 h-8 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center font-mono text-[10px] font-bold shrink-0">
                    {q.symbol.slice(0, 3)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-mono font-semibold text-sm text-[#0e1f1a]">{q.symbol}</p>
                    <p className="text-[10px] text-[#5c6b66] truncate">{q.name}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-mono text-xs text-[#0e1f1a]">${fmtPrice(q.price)}</p>
                    <p className={`font-mono text-[10px] flex items-center justify-end ${up ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                      <TrendIcon size={10} weight="bold" />
                      {fmtPct(q.change_percent)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </TabsContent>
      </Tabs>
    </aside>
  );
}

function AlertForm({ currentSymbol, onSubmit }) {
  const [price, setPrice] = React.useState("");
  const [direction, setDirection] = React.useState("above");

  const submit = (e) => {
    e.preventDefault();
    if (!currentSymbol || !price) return;
    onSubmit({ symbol: currentSymbol, target_price: parseFloat(price), direction });
    setPrice("");
  };

  return (
    <form onSubmit={submit} className="space-y-2 p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
      <p className="label-small">Nueva alerta — {currentSymbol || "—"}</p>
      <Select value={direction} onValueChange={setDirection}>
        <SelectTrigger data-testid="alert-direction" className="h-9 bg-white border-[#e5e0d8] text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="above">Por encima de</SelectItem>
          <SelectItem value="below">Por debajo de</SelectItem>
        </SelectContent>
      </Select>
      <Input
        data-testid="alert-price"
        type="number"
        step="0.01"
        placeholder="Precio objetivo"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        className="h-9 bg-white border-[#e5e0d8] font-mono text-xs"
      />
      <Button
        data-testid="submit-alert"
        type="submit"
        disabled={!currentSymbol || !price}
        className="w-full h-9 bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono text-xs"
      >
        Crear alerta
      </Button>
    </form>
  );
}
