import Link from "next/link";

export const metadata = { title: "Privacy · Mini-League Planner" };

// Keep this page true to what the code does. If tracking, sign-in or storage changes, update it.

const CONTACT = "nikhilphilip332@gmail.com"; // Nikhil's choice of public contact (24 Nov 2026)
export default function PrivacyPage() {
  return (
    <main className="flex flex-col gap-4 text-[14px] leading-relaxed text-text2">
      <Link href="/" className="text-[13px] font-semibold no-underline">← Back to the planner</Link>
      <h1 className="m-0 font-display text-2xl font-bold text-text">Privacy</h1>
      <p className="m-0 text-xs text-text3">Last updated 24 November 2026 (where visits come from, contact email)</p>

      <Section title="The short version">
        Mini-League Planner is a free hobby project. It works from public Fantasy Premier League data. You never need an
        account, and we never ask for your FPL password. Signing in with Google is optional.
      </Section>

      <Section title="What you give us">
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
          <li>
            <b>A team or league ID or link.</b> We use it to fetch public FPL data (squads, standings, points), the same data
            anyone can see on the FPL website.
          </li>
          <li>
            <b>Feedback you choose to send</b> (👍/👎 and any note). It&apos;s kept in our server logs and our usage stats,
            without your team ID.
          </li>
          <li>
            <b>If you sign in with Google</b> (optional): your name and email address. We use them only to see how the app is
            used, by person. We don&apos;t access anything else in your Google account.
          </li>
        </ul>
      </Section>

      <Section title="Usage stats">
        We count things like pages opened, strategies picked and plans viewed, using PostHog (hosted in the EU). If you
        aren&apos;t signed in, you&apos;re a random ID, not a name. Team and league numbers are removed from page addresses
        before anything is sent. We also note the gameweek you&apos;re planning, whether you opened the app inside
        another app (for example LinkedIn or WhatsApp), and where the visit came from (a campaign tag on the link, or a
        shared plan or invite). When something breaks (a crash or a failed request), we record the error message and
        the kind of page, with the same numbers removed. There are no screen recordings and no advertising trackers.
      </Section>

      <Section title="On your device">
        Your browser remembers the last team you opened and your light/dark choice, so the start page can offer &ldquo;Open
        my team&rdquo;. &ldquo;Forget this team&rdquo; clears it. It also remembers that you&apos;ve closed the
        first-visit tips or the home-screen hint, and counts your visits so that hint waits until your second. An invite link you share contains your league&apos;s number only, never your team. Drafts you save in what-if are kept in your browser too,
        and never sent to us except to score them. If you sign in, a login cookie keeps you signed in.
      </Section>

      <Section title="AI explanations">
        The short &ldquo;why this plan&rdquo; reasons are written by Anthropic&apos;s Claude from the plan&apos;s numbers
        (players, fixtures, expected points). No names of managers, team IDs, emails or other personal details are sent.
        Claude never chooses players; our optimizer does.
      </Section>

      <Section title="Who handles data for us">
        Vercel (the website), Render (the server and its logs, which include IP addresses as standard), PostHog (usage
        stats), Anthropic (AI explanations, plan numbers only) and Google (sign-in, if you use it). We don&apos;t sell or
        share data with anyone else.
      </Section>

      <Section title="Questions or deletion">
        Email <a href={`mailto:${CONTACT}`}>{CONTACT}</a> with any question, or to ask us to delete the usage stats tied to
        your Google email. (<b>Send feedback</b> in the app is anonymous, so we can&apos;t reply to it.)
      </Section>

      <p className="m-0 text-xs text-text3">
        Mini-League Planner isn&apos;t affiliated with the Premier League or Fantasy Premier League.
      </p>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h2 className="m-0 font-display text-base font-bold text-text">{title}</h2>
      <div>{children}</div>
    </section>
  );
}
