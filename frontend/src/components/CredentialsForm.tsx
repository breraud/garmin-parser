"use client";

import type { FormEvent } from "react";

import { ExportOptions } from "./ExportOptions";
import type {
  BatchExportFormat,
  ExportFormValues,
  RecentActivitySummary,
} from "@/lib/types";

interface CredentialsFormProps {
  values: ExportFormValues;
  loading: boolean;
  authLoading: boolean;
  authenticated: boolean;
  authMessage: string;
  activities: RecentActivitySummary[];
  activitiesLoading: boolean;
  activitiesError: string;
  onChange: (values: ExportFormValues) => void;
  onLogin: (values: ExportFormValues) => Promise<void>;
  onLogout: () => Promise<void>;
  onSubmit: (values: ExportFormValues) => Promise<void>;
}

export function CredentialsForm({
  values,
  loading,
  authLoading,
  authenticated,
  authMessage,
  activities,
  activitiesLoading,
  activitiesError,
  onChange,
  onLogin,
  onLogout,
  onSubmit,
}: CredentialsFormProps) {
  function updateField(field: keyof ExportFormValues, value: string) {
    onChange({
      ...values,
      [field]: value,
    });
  }

  function updateSelectedActivityIds(selectedActivityIds: string[]) {
    onChange({
      ...values,
      selectedActivityIds,
    });
  }

  function updateBatchExportFormat(batchExportFormat: BatchExportFormat) {
    onChange({
      ...values,
      batchExportFormat,
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(values);
  }

  async function handleLoginClick() {
    await onLogin(values);
  }

  async function handleLogoutClick() {
    await onLogout();
  }

  return (
    <form className="export-form" onSubmit={handleSubmit}>
      <div className="form-grid">
        <label className="field">
          <span>Email Garmin</span>
          <input
            name="email"
            type="email"
            value={values.email}
            onChange={(event) => updateField("email", event.target.value)}
            disabled={loading || authLoading}
            required
            autoComplete="username"
            placeholder="runner@example.com"
          />
        </label>

        <label className="field">
          <span>Mot de passe Garmin</span>
          <input
            name="password"
            type="password"
            value={values.password}
            onChange={(event) => updateField("password", event.target.value)}
            disabled={loading || authLoading}
            required
            autoComplete="current-password"
            placeholder="Mot de passe"
          />
        </label>
      </div>

      <div className="button-row">
        <button
          className="primary-button"
          type="button"
          onClick={handleLoginClick}
          disabled={loading || authLoading || !values.email.trim() || !values.password}
        >
          {authLoading ? "Connexion en cours" : authenticated ? "Reconnecter Garmin" : "Se connecter"}
        </button>
        {authenticated ? (
          <button
            className="primary-button"
            type="button"
            onClick={handleLogoutClick}
            disabled={loading || authLoading || !values.email.trim()}
          >
            Déconnexion
          </button>
        ) : null}
        {authMessage ? <span>{authMessage}</span> : null}
      </div>

      <ExportOptions
        mode={values.mode}
        selectedActivityIds={values.selectedActivityIds}
        batchExportFormat={values.batchExportFormat}
        activities={activities}
        activitiesLoading={activitiesLoading}
        activitiesError={activitiesError}
        dateFrom={values.dateFrom}
        dateTo={values.dateTo}
        maxActivities={values.maxActivities}
        notes={values.notes}
        disabled={loading}
        onModeChange={(value) => updateField("mode", value)}
        onSelectedActivityIdsChange={updateSelectedActivityIds}
        onBatchExportFormatChange={updateBatchExportFormat}
        onDateFromChange={(value) => updateField("dateFrom", value)}
        onDateToChange={(value) => updateField("dateTo", value)}
        onMaxActivitiesChange={(value) => updateField("maxActivities", value)}
        onNotesChange={(value) => updateField("notes", value)}
      />

      <button className="primary-button" type="submit" disabled={loading}>
        {loading ? "Generation en cours" : "Generer le Markdown"}
      </button>
    </form>
  );
}
