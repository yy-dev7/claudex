import { Eye, EyeOff } from 'lucide-react';
import { Button, Input } from '@/components/ui';
import { cn } from '@/utils/cn';
import type { HelperTextLink, HelperTextCode } from '@/types';

export interface SecretInputProps {
  value: string;
  placeholder: string;
  isVisible: boolean;
  onChange: (newValue: string) => void;
  onToggleVisibility: () => void;
  helperText?: HelperTextLink | HelperTextCode;
  containerClassName?: string;
  inputClassName?: string;
  buttonClassName?: string;
}

const renderHelperText = (helperText?: HelperTextLink | HelperTextCode) => {
  if (!helperText) return null;

  if ('code' in helperText) {
    return (
      <p className="mt-1.5 break-words text-2xs text-text-quaternary dark:text-text-dark-quaternary">
        {helperText.prefix}{' '}
        <code className="break-all rounded bg-surface-secondary px-1 py-0.5 text-text-primary dark:bg-surface-dark-secondary dark:text-text-dark-primary">
          {helperText.code}
        </code>{' '}
        {helperText.suffix}
      </p>
    );
  } else {
    return (
      <p className="mt-1.5 break-words text-2xs text-text-quaternary dark:text-text-dark-quaternary">
        {helperText.prefix}{' '}
        <a
          href={helperText.href}
          target="_blank"
          rel="noopener noreferrer"
          className="break-all text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
        >
          {helperText.anchorText}
        </a>
      </p>
    );
  }
};

export const SecretInput: React.FC<SecretInputProps> = ({
  value,
  placeholder,
  isVisible,
  onChange,
  onToggleVisibility,
  helperText,
  containerClassName = 'mt-2',
  inputClassName,
  buttonClassName,
}) => (
  <div className={containerClassName}>
    <div className="relative">
      <Input
        type={isVisible ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn('pr-9 text-xs', inputClassName)}
      />
      <Button
        type="button"
        onClick={onToggleVisibility}
        variant="ghost"
        size="icon"
        className={cn(
          'absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 text-text-tertiary hover:text-text-secondary dark:text-text-dark-tertiary dark:hover:text-text-dark-secondary',
          buttonClassName,
        )}
        aria-label={isVisible ? 'Hide value' : 'Show value'}
      >
        {isVisible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </Button>
    </div>
    {renderHelperText(helperText)}
  </div>
);
