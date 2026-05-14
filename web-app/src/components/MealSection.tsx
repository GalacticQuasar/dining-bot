import type { Meal } from "../types";
import StationCard from "./StationCard";

export default function MealSection({ meal, index }: { meal: Meal; index: number }) {
  const isOpen = meal.status.toLowerCase() !== "closed";

  return (
    <div
      className="animate-fade-in-up"
      style={{ animationDelay: `${index * 120}ms` }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="h-px flex-1 bg-border-subtle" />
        <div className="flex items-center gap-3 px-4">
          <h3 className="font-display text-xl font-semibold text-text-primary tracking-wide">
            {meal.name}
          </h3>
          <span
            className={`font-body text-[11px] font-medium tracking-wider uppercase px-2.5 py-1 rounded-full ${
              isOpen
                ? "bg-green-badge/60 text-green-badge-text border border-green-badge-text/15"
                : "bg-red-badge/60 text-red-badge-text border border-red-badge-text/15"
            }`}
          >
            {meal.status}
          </span>
        </div>
        <div className="h-px flex-1 bg-border-subtle" />
      </div>

      {!isOpen ? (
        <p className="font-body text-sm text-text-muted italic text-center py-4">
          Closed for this meal period.
        </p>
      ) : meal.stations.length === 0 ? (
        <p className="font-body text-sm text-text-muted italic text-center py-4">
          No stations available.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {meal.stations.map((station) => (
            <StationCard key={station.name} station={station} />
          ))}
        </div>
      )}
    </div>
  );
}