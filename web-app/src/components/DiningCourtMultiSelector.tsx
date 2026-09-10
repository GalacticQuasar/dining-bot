import type { DiningCourt, DiningCourtCategory } from "../types";

interface Props {
  categories: DiningCourtCategory[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

export default function DiningCourtMultiSelector({
  categories,
  selected,
  onChange,
}: Props) {
  const allCourts: DiningCourt[] = categories.flatMap((c) => c.diningCourts);

  const toggle = (name: string) => {
    if (selected.includes(name)) {
      onChange(selected.filter((n) => n !== name));
    } else {
      onChange([...selected, name]);
    }
  };

  const selectAll = () => onChange(allCourts.map((c) => c.name));
  const clearAll = () => onChange([]);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="block font-body text-xs font-medium tracking-[0.2em] uppercase text-gold-dim">
          Dining Courts
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={selectAll}
            className="font-body text-[11px] text-gold-dim hover:text-gold transition-colors cursor-pointer"
          >
            All
          </button>
          <span className="text-text-muted text-[11px]">·</span>
          <button
            type="button"
            onClick={clearAll}
            className="font-body text-[11px] text-gold-dim hover:text-gold transition-colors cursor-pointer"
          >
            None
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {allCourts.map((court) => {
          const isActive = selected.includes(court.name);
          return (
            <button
              key={court.name}
              type="button"
              onClick={() => toggle(court.name)}
              className={`rounded-lg border px-3 py-1.5 font-body text-sm transition-all duration-200 cursor-pointer ${
                isActive
                  ? "border-gold bg-gold-muted text-gold-bright shadow-[0_0_20px_rgba(207,184,124,0.1)]"
                  : "border-border-subtle bg-surface-2/60 text-text-secondary hover:border-border-gold hover:text-text-primary"
              }`}
            >
              {court.formalName}
            </button>
          );
        })}
      </div>
    </div>
  );
}