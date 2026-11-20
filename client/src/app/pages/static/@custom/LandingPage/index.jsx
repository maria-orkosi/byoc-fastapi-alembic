import { Code2, Search, Rocket } from 'lucide-react';
import { Link } from '../../../../../components/ui/Link';

/**
 * @param {object} props
 * @param {string} [props.className]
 */
function Hero({ className }) {
  return (
    <section className={`py-20 px-4 ${className || ''}`}>
      <div className="max-w-6xl mx-auto flex flex-col items-center text-center gap-6">
        <div className="flex items-center gap-3">
          <span className="font-[var(--font-heading)] text-2xl font-bold text-[var(--brand-primary)]">
            BFA
          </span>
          <span className="font-[var(--font-heading)] text-xl font-semibold text-[var(--brand-text)]">
            Byoc FastAPI Alembic r5c
          </span>
        </div>
        <h1 className="text-4xl font-bold text-[var(--brand-text)] max-w-2xl">
          Byoc FastAPI Alembic r5c runs on Orkosi from its own code
        </h1>
        <p className="text-lg text-[var(--brand-text-muted)] max-w-xl">
          Byoc FastAPI Alembic r5c is brought to Orkosi as its own code and run as it is:
          every part detected, placed and deployed without a remake.
        </p>
        <Link href="/signup" size="lg">
          Get started
        </Link>
      </div>
    </section>
  );
}

/**
 * @param {object} props
 * @param {string} [props.className]
 */
function FeatureGrid({ className }) {
  const features = [
    {
      icon: Search,
      title: 'Automatic code detection',
      description:
        'Your code is analyzed and every part is identified so nothing is missed during deployment.',
    },
    {
      icon: Code2,
      title: 'Zero-config placement',
      description:
        'Components are placed exactly where they belong without manual configuration or setup scripts.',
    },
    {
      icon: Rocket,
      title: 'Deployment without rewrites',
      description:
        'Your code runs on Orkosi as it is. Every part is detected, placed and deployed without a remake.',
    },
  ];

  return (
    <section className={`py-20 px-4 bg-[var(--brand-surface)] ${className || ''}`}>
      <div className="max-w-6xl mx-auto">
        <h2 className="text-3xl font-bold text-center text-[var(--brand-text)] mb-12">
          What Byoc FastAPI Alembic r5c does
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <div key={index} className="text-center rounded-lg border bg-card p-6">
              <div className="mx-auto mb-4 text-[var(--brand-primary)]">
                <feature.icon size={40} />
              </div>
              <h3 className="text-xl font-semibold text-[var(--brand-text)] mb-2">
                {feature.title}
              </h3>
              <p className="text-[var(--brand-text-muted)]">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/**
 * @param {object} props
 * @param {string} [props.className]
 */
function Steps({ className }) {
  const steps = [
    {
      number: 1,
      title: 'Bring your code',
      description:
        'Connect your repository with your existing FastAPI and Alembic setup. No changes to your codebase are required.',
    },
    {
      number: 2,
      title: 'Automatic detection',
      description:
        'Orkosi detects every part of your application: the backend framework, the database migrations, and the runtime requirements.',
    },
    {
      number: 3,
      title: 'Deploy and run',
      description:
        'Your code is placed and deployed as it is. Every part runs without a single rewrite or modification.',
    },
  ];

  return (
    <section className={`py-20 px-4 ${className || ''}`}>
      <div className="max-w-4xl mx-auto">
        <h2 className="text-3xl font-bold text-center text-[var(--brand-text)] mb-12">
          How it works
        </h2>
        <div className="space-y-8">
          {steps.map((step, index) => (
            <div key={index} className="flex items-start gap-4">
              <span className="text-lg font-bold shrink-0 w-10 h-10 flex items-center justify-center rounded-full border border-[var(--brand-primary)] text-[var(--brand-primary)]">
                {step.number}
              </span>
              <div>
                <h3 className="text-xl font-semibold text-[var(--brand-text)] mb-2">
                  {step.title}
                </h3>
                <p className="text-[var(--brand-text-muted)]">{step.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
/**
 * @param {object} props
 * @param {string} [props.className]
 */
function Testimonials({ className }) {
  const testimonials = [
    {
      quote: "Your customer's words go here",
      author: 'Customer name, company',
    },
    {
      quote: "Your customer's words go here",
      author: 'Customer name, company',
    },
    {
      quote: "Your customer's words go here",
      author: 'Customer name, company',
    },
  ];

  return (
    <section className={`py-20 px-4 bg-[var(--brand-surface)] ${className || ''}`}>
      <div className="max-w-6xl mx-auto">
        <h2 className="text-3xl font-bold text-center text-[var(--brand-text)] mb-12">
          Teams that deploy with us
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {testimonials.map((item, index) => (
            <div key={index} className="rounded-lg border bg-card p-6 pt-6">
              <div className="mb-4">
                <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold">Placeholder</span>
              </div>
              <p className="text-[var(--brand-text-muted)] italic mb-4">
                &ldquo;{item.quote}&rdquo;
              </p>
              <p className="text-sm font-medium text-[var(--brand-text)]">
                &mdash; {item.author}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/**
 * @param {object} props
 * @param {string} [props.className]
 */
function PricingTable({ className }) {
  const plans = [
    {
      name: 'Free',
      price: '$0',
      period: '/month',
      features: [
        'Basic code detection',
        'Standard deployment pipeline',
        'Community support',
      ],
    },
    {
      name: 'Pro',
      price: '$49',
      period: '/month',
      features: [
        'Everything in Free',
        'Priority deployment',
        'Advanced detection rules',
        'Dedicated support',
      ],
    },
  ];

  return (
    <section className={`py-20 px-4 ${className || ''}`}>
      <div className="max-w-5xl mx-auto">
        <h2 className="text-3xl font-bold text-center text-[var(--brand-text)] mb-12">
          Pricing
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-3xl mx-auto">
          {plans.map((plan, index) => (
            <div key={index} className={`rounded-lg border bg-card p-6 ${index === 1 ? 'border-[var(--brand-primary)]' : ''}`}>
              <h3 className="text-2xl font-bold text-[var(--brand-text)] mb-2">
                {plan.name}
              </h3>
              <div className="mt-2 mb-4">
                <span className="text-4xl font-bold text-[var(--brand-text)]">{plan.price}</span>
                <span className="text-[var(--brand-text-muted)]">{plan.period}</span>
              </div>
              <ul className="space-y-3 mb-6">
                {plan.features.map((feature, fi) => (
                  <li key={fi} className="flex items-start gap-2">
                    <p className="text-[var(--brand-text-muted)]">{feature}</p>
                  </li>
                ))}
              </ul>
              <Link href="/signup" size="sm" className="w-full">
                Get started
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
/**
 * @param {object} props
 * @param {string} [props.className]
 */
function Faq({ className }) {
  const questions = [
    {
      question: 'What is Byoc FastAPI Alembic r5c?',
      answer:
        'Byoc FastAPI Alembic r5c is a bring-your-own-code platform that runs on Orkosi. Your existing FastAPI application with Alembic migrations is brought to Orkosi as its own code and runs as it is, with every part detected, placed, and deployed without a remake.',
    },
    {
      question: 'Who is it for?',
      answer:
        'It is built for SaaS teams who use FastAPI with Alembic and want to deploy their application on Orkosi without rewriting or migrating their codebase. Your application is detected and deployed exactly as you wrote it.',
    },
    {
      question: 'How do I get started?',
      answer:
        'Connect your repository that contains a FastAPI application with Alembic migrations. Orkosi detects every part of your code, places it in the right environment, and deploys it. No configuration files or setup scripts are needed.',
    },
    {
      question: 'What does it cost?',
      answer:
        'Byoc FastAPI Alembic r5c offers a Free tier with basic code detection and standard deployment. The Pro tier at $49 per month adds priority deployment, advanced detection rules, and dedicated support.',
    },
    {
      question: 'How does deployment work?',
      answer:
        'Your code is brought to Orkosi as its own code and run as it is. Every part is detected, placed, and deployed without a remake, so your application runs exactly as you wrote it.',
    },
  ];

  return (
    <section className={`py-20 px-4 bg-[var(--brand-surface)] ${className || ''}`}>
      <div className="max-w-3xl mx-auto">
        <h2 className="text-3xl font-bold text-center text-[var(--brand-text)] mb-12">
          Frequently asked questions
        </h2>
        <div className="space-y-2">
          {questions.map((item, index) => (
            <details key={index} className="rounded-lg border bg-card">
              <summary className="text-left text-lg font-medium text-[var(--brand-text)] p-4 cursor-pointer">
                {item.question}
              </summary>
              <div className="px-4 pb-4">
                <p className="text-[var(--brand-text-muted)]">{item.answer}</p>
              </div>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

/**
 * @param {object} props
 * @param {string} [props.className]
 */
function CallToAction({ className }) {
  return (
    <section className={`py-20 px-4 ${className || ''}`}>
      <div className="max-w-2xl mx-auto text-center">
        <h2 className="text-3xl font-bold text-[var(--brand-text)] mb-4">
          Byoc FastAPI Alembic r5c runs on Orkosi from its own code
        </h2>
        <p className="text-lg text-[var(--brand-text-muted)] mb-8">
          Bring your FastAPI and Alembic code. Every part is detected, placed, and deployed without
          a remake.
        </p>
        <Link href="/signup" size="lg">
          Get started
        </Link>
      </div>
    </section>
  );
}

/**
 * LandingPage — the public landing page for Byoc FastAPI Alembic r5c.
 */
export function LandingPage() {
  return (
    <main>
      <Hero />
      <FeatureGrid />
      <Steps />
      <Testimonials />
      <PricingTable />
      <Faq />
      <CallToAction />
    </main>
  );
}