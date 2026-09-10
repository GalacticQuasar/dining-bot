export type MealName = "Breakfast" | "Lunch" | "Dinner";

const MEAL_OPTIONS: MealName[] = ["Breakfast", "Lunch", "Dinner"];

interface Props {
  selected: MealName;
  onChange: (meal: MealName) => void;
}

export default function MealSelector({ selected, onChange }: Props) {
  return (
    <div>
      <label className="block font-body text-xs font-medium tracking-[0.2em] uppercase text-gold-dim mb-2">
        Meal
      </label>
      <div className="flex gap-2">
        {MEAL_OPTIONS.map((meal) => {
          const isActive = meal === selected;
          return (
            <button
              key={meal}
              type="button"
              onClick={() => onChange(meal)}
              className={`flex-1 rounded-lg border px-4 py-2.5 font-body text-sm transition-all duration-200 cursor-pointer ${
                isActive
                  ? "border-gold bg-gold-muted text-gold-bright shadow-[0_0_20px_rgba(207,184,124,0.1)]"
                  : "border-border-subtle bg-surface-2/60 text-text-secondary hover:border-border-gold hover:text-text-primary"
              }`}
            >
              {meal}
            </button>
          );
        })}
      </div>
    </div>
  );
}