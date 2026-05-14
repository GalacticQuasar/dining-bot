import type { DiningCourt, DiningCourtCategory } from "../types";

interface Props {
  categories: DiningCourtCategory[];
  selected: string;
  onChange: (court: DiningCourt) => void;
}

export default function DiningCourtSelector({ categories, selected, onChange }: Props) {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const [catIndex, courtIndex] = e.target.value.split("-").map(Number);
    const court = categories[catIndex].diningCourts[courtIndex];
    onChange(court);
  };

  const selectedValue = (() => {
    for (let ci = 0; ci < categories.length; ci++) {
      for (let di = 0; di < categories[ci].diningCourts.length; di++) {
        if (categories[ci].diningCourts[di].name === selected) {
          return `${ci}-${di}`;
        }
      }
    }
    return "";
  })();

  return (
    <div>
      <label
        htmlFor="court-select"
        className="block font-body text-xs font-medium tracking-[0.2em] uppercase text-gold-dim mb-2"
      >
        Dining Court
      </label>
      <select
        id="court-select"
        value={selectedValue}
        onChange={handleChange}
        className="w-full rounded-lg border border-border-gold bg-surface-2 px-4 py-2.5 font-body text-sm text-text-primary shadow-none focus:border-gold focus:ring-1 focus:ring-gold/30 focus:outline-none appearance-none cursor-pointer transition-colors"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='%23CFB87C' viewBox='0 0 16 16'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E")`,
          backgroundRepeat: "no-repeat",
          backgroundPosition: "right 12px center",
          backgroundSize: "16px",
        }}
      >
        <option value="" disabled>
          Select a dining court
        </option>
        {categories.map((cat, ci) => (
          <optgroup key={cat.name} label={cat.name}>
            {cat.diningCourts.map((court, di) => (
              <option key={court.name} value={`${ci}-${di}`}>
                {court.formalName}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}