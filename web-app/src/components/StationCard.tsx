import type { Station } from "../types";
import TraitBadge from "./TraitBadge";

export default function StationCard({ station }: { station: Station }) {
  const items = station.items
    .map((si) => si.item)
    .filter((item): item is NonNullable<typeof item> => item !== null);

  if (items.length === 0) return null;

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-2/50 backdrop-blur-sm p-4 transition-all duration-200 hover:border-border-gold hover:bg-surface-3/50">
      <h4 className="font-body font-semibold text-gold text-sm tracking-wide uppercase mb-3">
        {station.name}
      </h4>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.name} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="font-body text-sm text-text-primary">{item.name}</span>
            {(item.traits?.length ?? 0) > 0 && (
              <span className="flex flex-wrap gap-1">
                {item.traits.map((t) => (
                  <TraitBadge key={t.name} trait={t} />
                ))}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}