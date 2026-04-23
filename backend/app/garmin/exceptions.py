class GarminClientError(Exception):
    """Base exception for Garmin integration failures."""


class GarminAuthenticationError(GarminClientError):
    """Raised when Garmin rejects credentials or an authenticated session."""


class GarminMFARequiredError(GarminAuthenticationError):
    """Raised when Garmin requires a second authentication factor."""


class GarminRateLimitError(GarminClientError):
    """Raised when Garmin rate-limits requests."""


class GarminConnectionError(GarminClientError):
    """Raised when Garmin cannot be reached or returns an unexpected transport error."""


class GarminActivityNotFoundError(GarminClientError):
    """Raised when a requested Garmin activity cannot be found."""

