import React, { useId, useState } from 'react';

/**
 * Input field whose label acts as the placeholder when empty
 * and smoothly floats to the top border when focused or filled.
 */
export const FloatingInput = ({
  label,
  type = 'text',
  value = '',
  onChange,
  required = false,
  minLength,
  maxLength,
  autoComplete,
  hasError = false,
  leftIcon = null,
  rightElement = null,
  inputClassName = '',
}) => {
  const inputId = useId();
  const [focused, setFocused] = useState(false);

  const isFilled = value !== undefined && value !== null && String(value).length > 0;
  const isFloating = focused || isFilled;

  const leftPad = leftIcon ? 'pl-10' : 'px-3.5';
  const rightPad = rightElement ? 'pr-10' : 'pr-3.5';
  const idleLabelLeft = leftIcon ? 'left-10' : 'left-3.5';

  const borderClasses = hasError
    ? 'border-rose-300 focus:ring-rose-500'
    : 'border-slate-200 focus:ring-brand-primary focus:border-brand-primary';

  const floatingLabelColor = hasError
    ? 'text-rose-600'
    : focused
    ? 'text-brand-primary'
    : 'text-slate-600';

  return (
    <div className="relative">
      {leftIcon && (
        <span
          className={`absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none transition-colors duration-200 ${
            focused ? 'text-brand-primary' : 'text-slate-400'
          }`}
        >
          {leftIcon}
        </span>
      )}

      <input
        id={inputId}
        type={type}
        required={required}
        minLength={minLength}
        maxLength={maxLength}
        autoComplete={autoComplete}
        value={value}
        onChange={onChange}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder=" "
        className={`peer w-full h-11 ${leftPad} ${rightPad} rounded-lg border bg-surface-card text-xs text-slate-900 focus:outline-none focus:ring-2 transition-all duration-200 ${borderClasses} ${inputClassName}`}
      />

      <label
        htmlFor={inputId}
        className={`pointer-events-none select-none absolute transition-all duration-200 ease-out rounded-sm ${
          isFloating
            ? `-top-2 translate-y-0 left-3 px-1 bg-surface-card text-[11px] font-semibold ${floatingLabelColor}`
            : `top-1/2 -translate-y-1/2 ${idleLabelLeft} text-xs text-slate-400 peer-focus:-top-2 peer-focus:translate-y-0 peer-focus:left-3 peer-focus:px-1 peer-focus:bg-surface-card peer-focus:text-[11px] peer-focus:font-semibold peer-focus:text-brand-primary peer-[:not(:placeholder-shown)]:-top-2 peer-[:not(:placeholder-shown)]:translate-y-0 peer-[:not(:placeholder-shown)]:left-3 peer-[:not(:placeholder-shown)]:px-1 peer-[:not(:placeholder-shown)]:bg-surface-card peer-[:not(:placeholder-shown)]:text-[11px] peer-[:not(:placeholder-shown)]:font-semibold`
        }`}
      >
        {label}
      </label>

      {rightElement && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center">
          {rightElement}
        </div>
      )}
    </div>
  );
};

