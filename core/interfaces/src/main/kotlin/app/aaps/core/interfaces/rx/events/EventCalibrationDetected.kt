package app.aaps.core.interfaces.rx.events

/** Fired when a finger-stick calibration is detected — either from a CGM source
 *  (Dexcom, Glunovo, Intelligo) inserting a FINGER_STICK_BG_VALUE therapy event,
 *  or from the AAPS CalibrationDialog sending a calibration to xDrip.
 *
 *  Consumers can use this to impose a temporary hold on aggressive dosing while
 *  CGM readings stabilise after calibration. */
class EventCalibrationDetected : Event()
