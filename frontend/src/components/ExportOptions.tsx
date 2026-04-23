import type { ChangeEvent } from "react";

import type {
  BatchExportFormat,
  ExportMode,
  RecentActivitySummary,
} from "@/lib/types";

interface ExportOptionsProps {
  mode: ExportMode;
  selectedActivityIds: string[];
  batchExportFormat: BatchExportFormat;
  activities: RecentActivitySummary[];
  activitiesLoading?: boolean;
  activitiesError?: string;
  dateFrom: string;
  dateTo: string;
  maxActivities: string;
  notes: string;
  disabled?: boolean;
  onModeChange: (value: ExportMode) => void;
  onSelectedActivityIdsChange: (value: string[]) => void;
  onBatchExportFormatChange: (value: BatchExportFormat) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onMaxActivitiesChange: (value: string) => void;
  onNotesChange: (value: string) => void;
}

export function ExportOptions({
  mode,
  selectedActivityIds,
  batchExportFormat,
  activities,
  activitiesLoading = false,
  activitiesError = "",
  dateFrom,
  dateTo,
  maxActivities,
  notes,
  disabled = false,
  onModeChange,
  onSelectedActivityIdsChange,
  onBatchExportFormatChange,
  onDateFromChange,
  onDateToChange,
  onMaxActivitiesChange,
  onNotesChange,
}: ExportOptionsProps) {
  function handleModeChange(event: ChangeEvent<HTMLInputElement>) {
    onModeChange(event.target.value as ExportMode);
  }

  function handleActivityToggle(activityId: string, checked: boolean) {
    if (mode === "single_activity") {
      onSelectedActivityIdsChange(checked ? [activityId] : []);
      return;
    }

    if (checked) {
      onSelectedActivityIdsChange(
        selectedActivityIds.includes(activityId)
          ? selectedActivityIds
          : [...selectedActivityIds, activityId],
      );
      return;
    }

    onSelectedActivityIdsChange(
      selectedActivityIds.filter((selectedActivityId) => selectedActivityId !== activityId),
    );
  }

  function handleDateFromChange(event: ChangeEvent<HTMLInputElement>) {
    onDateFromChange(event.target.value);
  }

  function handleDateToChange(event: ChangeEvent<HTMLInputElement>) {
    onDateToChange(event.target.value);
  }

  function handleMaxActivitiesChange(event: ChangeEvent<HTMLInputElement>) {
    onMaxActivitiesChange(event.target.value);
  }

  function handleNotesChange(event: ChangeEvent<HTMLTextAreaElement>) {
    onNotesChange(event.target.value);
  }

  function handleBatchExportFormatChange(event: ChangeEvent<HTMLInputElement>) {
    onBatchExportFormatChange(event.target.value as BatchExportFormat);
  }

  return (
    <>
      <fieldset className="mode-selector" disabled={disabled}>
        <legend>Mode d&apos;export</legend>
        <label>
          <input
            type="radio"
            name="mode"
            value="single_activity"
            checked={mode === "single_activity"}
            onChange={handleModeChange}
          />
          Activite unique
        </label>
        <label>
          <input
            type="radio"
            name="mode"
            value="multi_activity"
            checked={mode === "multi_activity"}
            onChange={handleModeChange}
          />
          Selection multiple
        </label>
        <label>
          <input
            type="radio"
            name="mode"
            value="date_range"
            checked={mode === "date_range"}
            onChange={handleModeChange}
          />
          Plage de dates
        </label>
      </fieldset>

      <div className="form-grid">
        {mode === "single_activity" || mode === "multi_activity" ? (
          <div className="field field-wide">
            <span>
              {mode === "single_activity"
                ? "Activite recente"
                : "Activites recentes a inclure dans le ZIP"}
            </span>
            <div className="activity-picker" role="group" aria-label="Activites recentes">
              {activitiesLoading ? (
                <p className="picker-message">Chargement des activites...</p>
              ) : activities.length === 0 ? (
                <p className="picker-message">Aucune seance trouvee (verifie tes acces)</p>
              ) : (
                activities.map((activity) => {
                  const checked = selectedActivityIds.includes(activity.activity_id);
                  return (
                    <label key={activity.activity_id} className="activity-option">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={(event) =>
                          handleActivityToggle(activity.activity_id, event.target.checked)
                        }
                      />
                      <span>
                        [{activity.date}] {activity.title ?? "Activite sans titre"} -{" "}
                        {activity.distance_km?.toFixed(2) ?? "-"} km
                      </span>
                    </label>
                  );
                })
              )}
            </div>
            {activitiesError ? <span>{activitiesError}</span> : null}
            {mode === "multi_activity" ? (
              <fieldset className="mode-selector batch-format-selector" disabled={disabled}>
                <legend>Format batch</legend>
                <label>
                  <input
                    type="radio"
                    name="batchExportFormat"
                    value="zip"
                    checked={batchExportFormat === "zip"}
                    onChange={handleBatchExportFormatChange}
                  />
                  Fichiers separes (ZIP)
                </label>
                <label>
                  <input
                    type="radio"
                    name="batchExportFormat"
                    value="markdown"
                    checked={batchExportFormat === "markdown"}
                    onChange={handleBatchExportFormatChange}
                  />
                  Fichier unique (Markdown long)
                </label>
              </fieldset>
            ) : null}
          </div>
        ) : (
          <>
            <label className="field">
              <span>Date de debut</span>
              <input
                name="dateFrom"
                type="date"
                value={dateFrom}
                onChange={handleDateFromChange}
                disabled={disabled}
                required
              />
            </label>
            <label className="field">
              <span>Date de fin</span>
              <input
                name="dateTo"
                type="date"
                value={dateTo}
                onChange={handleDateToChange}
                disabled={disabled}
                required
              />
            </label>
            <label className="field">
              <span>Nombre max d&apos;activites</span>
              <input
                name="maxActivities"
                type="number"
                min="1"
                max="100"
                value={maxActivities}
                onChange={handleMaxActivitiesChange}
                disabled={disabled}
                required
              />
            </label>
          </>
        )}

        <label className="field field-wide">
          <span>Notes et tags</span>
          <textarea
            name="notes"
            value={notes}
            onChange={handleNotesChange}
            disabled={disabled}
            rows={4}
            placeholder="#chaleur #chaussures #fatigue"
          />
        </label>
      </div>
    </>
  );
}
