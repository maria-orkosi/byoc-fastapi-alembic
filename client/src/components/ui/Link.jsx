import { forwardRef } from 'react';

/**
 * Link primitive — a styled anchor that uses brand design tokens.
 * Use this instead of raw `<a>` elements for navigation CTAs.
 *
 * @param {object} props
 * @param {React.ReactNode} props.children
 * @param {string} [props.className]
 * @param {'default'|'primary'} [props.variant]
 * @param {'default'|'sm'|'lg'} [props.size]
 */
const Link = forwardRef(function Link({ className, variant = 'primary', size = 'default', children, ...props }, ref) {
  const variantClasses = {
    default:
      'bg-[var(--brand-surface)] text-[var(--brand-text)] border border-[var(--brand-text-muted)] hover:bg-[var(--brand-bg)]',
    primary:
      'bg-[var(--brand-primary)] text-white hover:opacity-90',
  };

  const sizeClasses = {
    sm: 'px-4 py-2 text-sm',
    default: 'px-6 py-3',
    lg: 'px-8 py-4 text-lg',
  };

  return (
    <a
      ref={ref}
      className={`inline-flex items-center justify-center rounded-md font-medium transition-opacity ${variantClasses[variant] || variantClasses.primary} ${sizeClasses[size] || sizeClasses.default} ${className || ''}`}
      {...props}
    >
      {children}
    </a>
  );
});

export { Link };