import { Link } from '../../../../../components/ui/Link';

/**
 * @param {object} props
 * @param {string} [props.className]
 */
function Hero({ className }) {
  return (
    <section className={`py-20 px-4 ${className || ''}`}>
      <div className="max-w-md mx-auto text-center">
        <div className="flex items-center justify-center gap-3 mb-6">
          <span className="font-[var(--font-heading)] text-2xl font-bold text-[var(--brand-primary)]">
            BFA
          </span>
        </div>
        <h1 className="text-3xl font-bold text-[var(--brand-text)] mb-4">
          Get started
        </h1>
        <p className="text-lg text-[var(--brand-text-muted)] mb-8">
          Bring your FastAPI and Alembic code to Orkosi and have every part detected, placed, and
          deployed without a remake.
        </p>
        <Link href="/" size="lg">
          Back to home
        </Link>
      </div>
    </section>
  );
}

/**
 * SignupPage — the public sign-up page for Byoc FastAPI Alembic r5c.
 */
export function SignupPage() {
  return (
    <main>
      <Hero />
    </main>
  );
}