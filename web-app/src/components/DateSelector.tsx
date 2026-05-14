interface DayOption {
  date: Date;
  label: string;
  dayName: string;
  isoDate: string;
  isToday: boolean;
}

function buildDayOptions(): DayOption[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days: DayOption[] = [];

  for (let offset = -1; offset <= 6; offset++) {
    const d = new Date(today);
    d.setDate(d.getDate() + offset);
    const dayName = d.toLocaleDateString("en-US", { weekday: "long" });
    const isoDate = d.toISOString().split("T")[0];

    let label: string;
    if (offset === -1) label = "Yesterday";
    else if (offset === 0) label = "Today";
    else if (offset === 1) label = "Tomorrow";
    else label = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });

    days.push({
      date: d,
      label,
      dayName,
      isoDate,
      isToday: offset === 0,
    });
  }

  return days;
}

interface Props {
  selectedDate: string;
  onChange: (isoDate: string) => void;
}

export default function DateSelector({ selectedDate, onChange }: Props) {
  const days = buildDayOptions();

  return (
    <div>
      <label className="block font-body text-xs font-medium tracking-[0.2em] uppercase text-gold-dim mb-2">
        Date
      </label>
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
        {days.map((day) => {
          const isActive = day.isoDate === selectedDate;
          return (
            <button
              key={day.isoDate}
              type="button"
              onClick={() => onChange(day.isoDate)}
              className={`flex-shrink-0 flex flex-col items-center rounded-lg border px-4 py-2.5 text-sm font-body transition-all duration-200 cursor-pointer ${
                isActive
                  ? "border-gold bg-gold-muted text-gold-bright shadow-[0_0_20px_rgba(207,184,124,0.1)]"
                  : "border-border-subtle bg-surface-2/60 text-text-secondary hover:border-border-gold hover:text-text-primary"
              }`}
            >
              <span className={`font-medium leading-tight ${isActive ? "text-gold" : ""}`}>
                {day.label}
              </span>
              <span className={`text-[11px] mt-0.5 ${isActive ? "text-gold-dim" : "text-text-muted"}`}>
                {day.dayName}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}