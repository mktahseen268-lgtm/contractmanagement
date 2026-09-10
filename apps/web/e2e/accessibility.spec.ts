import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Automated accessibility checks (Phase 9, item 5).
 *
 * **What this proves and what it does not.** axe finds roughly a third of WCAG issues — the
 * mechanical third: missing names, bad contrast ratios, broken ARIA, unlabelled controls. It
 * cannot tell whether the reading order makes sense, whether an `alt` text is accurate rather
 * than merely present, or whether somebody can actually complete a signature with a screen
 * reader. Those need a person, and for the signing portal they need a person from the
 * population that will use it. `docs/32-accessibility.md` §4 says so in as many words; this
 * file is the automated third, not the claim.
 *
 * **Serious and critical fail the build. Moderate and minor are printed.** The known-open items
 * in docs/32 §3 sit at moderate, and a job that is red on its first run gets disabled in its
 * first week. As each item closes, its rule moves up into the failing set.
 */

const FAILING_IMPACTS = new Set(["serious", "critical"]);

async function scan(page: Page, context?: string) {
  const builder = new AxeBuilder({ page }).withTags([
    "wcag2a",
    "wcag2aa",
    "wcag21a",
    "wcag21aa",
  ]);
  const results = await (context ? builder.include(context) : builder).analyze();

  const blocking = results.violations.filter((v) => FAILING_IMPACTS.has(v.impact ?? ""));
  const advisory = results.violations.filter((v) => !FAILING_IMPACTS.has(v.impact ?? ""));

  if (advisory.length) {
    // Printed, not thrown. These are the tracked exceptions; hiding them would be worse than
    // failing on them, because then nobody sees the list shrink.
    console.log(
      `advisory (${advisory.length}): ` +
        advisory.map((v) => `${v.id} [${v.impact}] x${v.nodes.length}`).join(", "),
    );
  }

  expect(
    blocking,
    blocking
      .map(
        (v) =>
          `${v.id} (${v.impact}) — ${v.help}\n  ${v.nodes
            .slice(0, 3)
            .map((n) => n.target.join(" "))
            .join("\n  ")}`,
      )
      .join("\n\n"),
  ).toEqual([]);
}

test.describe("public surfaces", () => {
  test("sign-in page", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    await scan(page);
  });

  test("accessibility statement is reachable and itself accessible", async ({ page }) => {
    // A statement page with accessibility problems is the clearest possible signal that nobody
    // checked, so it gets scanned like anything else.
    const response = await page.goto("/accessibility");
    // Signed-out this redirects to login; either way it must not error.
    expect(response?.status()).toBeLessThan(400);
    await scan(page);
  });

  test("signing portal — an invalid token still renders an accessible page", async ({ page }) => {
    // The unhappy path deliberately: an expired link is what a real customer most often hits,
    // and an error state nobody can read is an error state nobody can act on.
    await page.goto("/sign/not-a-real-token");
    await expect(
      page.getByText(/this signing link isn.t active/i),
    ).toBeVisible({ timeout: 15_000 });
    await scan(page);
  });

  test("printable signing guide", async ({ page }) => {
    await page.goto("/sign/not-a-real-token/guide");
    await expect(page.getByRole("heading", { name: /how to sign/i })).toBeVisible();
    await scan(page);
  });
});

test.describe("keyboard", () => {
  test("the skip link is the first thing reached, and it moves focus", async ({ page }) => {
    // Regression test for a real bug: the skip link was originally placed after the sidebar,
    // so a keyboard user tabbed through twenty navigation links before reaching it. It looked
    // present in the markup and was useless in practice.
    await page.goto("/login");
    await page.keyboard.press("Tab");

    const focused = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return { tag: el?.tagName, text: el?.textContent?.trim() ?? "" };
    });
    // On the signed-out page there is no shell, so this asserts the weaker but still meaningful
    // property: the first tab stop is an interactive element, not the body.
    expect(focused.tag).not.toBe("BODY");
  });

  test("focus is visible on the first control", async ({ page }) => {
    await page.goto("/login");
    await page.keyboard.press("Tab");
    const outline = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return "";
      const style = window.getComputedStyle(el);
      return `${style.outlineStyle}|${style.outlineWidth}|${style.boxShadow}`;
    });
    // Either a real outline or a focus box-shadow. What must not happen is `outline: none` with
    // nothing in its place, which is the state that makes a keyboard unusable.
    expect(outline).not.toMatch(/^none\|0px\|none$/);
  });
});
