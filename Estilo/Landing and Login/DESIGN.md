---
name: Geovivienda Internal
colors:
  surface: '#f9f9f9'
  surface-dim: '#dadada'
  surface-bright: '#f9f9f9'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3f3'
  surface-container: '#eeeeee'
  surface-container-high: '#e8e8e8'
  surface-container-highest: '#e2e2e2'
  on-surface: '#1a1c1c'
  on-surface-variant: '#464650'
  inverse-surface: '#2f3131'
  inverse-on-surface: '#f1f1f1'
  outline: '#767681'
  outline-variant: '#c7c5d1'
  surface-tint: '#535a96'
  primary: '#181f59'
  on-primary: '#ffffff'
  primary-container: '#2f3670'
  on-primary-container: '#9aa1e3'
  inverse-primary: '#bdc2ff'
  secondary: '#705d00'
  on-secondary: '#ffffff'
  secondary-container: '#fddb4c'
  on-secondary-container: '#735f00'
  tertiary: '#540008'
  on-tertiary: '#ffffff'
  tertiary-container: '#7d0011'
  on-tertiary-container: '#ff7f7a'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dfe0ff'
  primary-fixed-dim: '#bdc2ff'
  on-primary-fixed: '#0c144f'
  on-primary-fixed-variant: '#3b427c'
  secondary-fixed: '#ffe16f'
  secondary-fixed-dim: '#e6c437'
  on-secondary-fixed: '#221b00'
  on-secondary-fixed-variant: '#544600'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ae'
  on-tertiary-fixed: '#410005'
  on-tertiary-fixed-variant: '#910617'
  background: '#f9f9f9'
  on-background: '#1a1c1c'
  surface-variant: '#e2e2e2'
  surface-white: '#FFFFFF'
  text-primary: '#1A1D35'
  border-subtle: '#E2E4E9'
typography:
  display-lg:
    fontFamily: Montserrat
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Montserrat
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Montserrat
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Montserrat
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-lg:
    fontFamily: Montserrat
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-md:
    fontFamily: Montserrat
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Montserrat
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Montserrat
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Montserrat
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
  label-sm:
    fontFamily: Montserrat
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  margin-page: 2rem
  gutter-grid: 1.5rem
  container-max: 1440px
  stack-sm: 0.5rem
  stack-md: 1rem
  stack-lg: 2rem
---

## Brand & Style

The design system is engineered for internal operational efficiency, focusing on clarity, trust, and precision. It serves as the digital backbone for Geovivienda, facilitating complex data management and real-estate workflows.

The aesthetic follows a **Modern Minimalism** approach. It prioritizes high legibility and a reduced cognitive load through generous whitespace and a disciplined color application. By avoiding gradients and textures, the interface maintains a professional, "tool-first" atmosphere that feels dependable and high-end. The visual language evokes a sense of organized stability, essential for institutional data handling.

## Colors

The palette is anchored by a deep navy blue, used strategically for navigation and core branding to establish authority. 

- **Primary (Navy Blue):** Reserved for high-level interaction points, sidebar backgrounds, and active states.
- **Accent 1 (Gold):** Utilized for positive reinforcement, top-tier compatibility scores, and high-priority callouts.
- **Accent 2 (Red):** Used sparingly for critical alerts, low scores, or destructive actions to ensure high visibility without overwhelming the layout.
- **Neutrals:** A combination of pure white for main content areas and a very light gray for structural separation. Text should utilize a softened version of the primary navy for better readability than pure black.

## Typography

This design system uses **Montserrat** exclusively to provide a unified, contemporary geometric feel. 

Headlines utilize heavier weights (600-700) to create a clear information hierarchy, while body text remains at a medium weight (400) for comfortable long-form reading. To ensure data density without sacrificing clarity, use `body-md` for table content and `label-md` for metadata or table headers. Tighten letter-spacing slightly on larger display sizes to maintain a sophisticated, compact appearance.

## Layout & Spacing

The layout follows a **Fixed Grid** philosophy for desktop to maintain structural integrity across different monitor sizes, transitioning to a fluid model for mobile devices.

- **Sidebar:** A fixed 280px sidebar provides persistent navigation.
- **Main Canvas:** A centered container with a maximum width of 1440px ensures data columns don't stretch excessively on ultrawide monitors.
- **Rhythm:** An 8px base unit controls all spacing. Margins between major sections should be 32px (4 units), while internal card padding should be 24px (3 units) to emphasize the minimalist, airy aesthetic.

## Elevation & Depth

To maintain a clean, flat aesthetic, this design system avoids heavy shadows. Instead, it utilizes **Tonal Layers** and **Soft Ambient Shadows**.

- **Level 0 (Background):** Pure White (#FFFFFF) for the primary workspace.
- **Level 1 (Surface):** Subtle light gray (#F8F8F8) used for secondary areas like the sidebar or background regions of the page.
- **Level 2 (Cards/Interactives):** White surfaces with a very soft, diffused shadow (Blur: 12px, Y: 4px, Opacity: 4%) and a thin, 1px neutral border (#E2E4E9). 
- **Active Elevation:** When a card is hovered, the shadow intensity increases slightly (Opacity: 8%) to provide tactile feedback without looking "heavy."

## Shapes

The design system adopts a **Rounded** shape language to soften the corporate nature of the application. 

Standard components (buttons, input fields, cards) use a 0.5rem (8px) radius. Larger containers or modals should scale up to 1rem (16px) to maintain visual harmony. Interactive elements should never be sharp, ensuring the tool feels approachable and modern.

## Components

- **Buttons:** Primary buttons use the Navy Blue background with White text. Accent buttons (Gold) are used for specific primary calls-to-action like "Generate Report." All buttons feature a subtle 8px corner radius.
- **Cards:** White background, 1px subtle border, and soft ambient shadow. Content within cards should follow the 24px internal padding rule.
- **Tables:** Rows should have a fixed height (56px) with a single-pixel horizontal divider (#F0F0F0). Avoid vertical borders. Use "Zebra striping" only for data-heavy views using #F8F8F8.
- **Input Fields:** Use a 1px border (#E2E4E9) that transitions to the Primary Navy on focus. Labels should be `label-md` placed above the field.
- **Sidebar:** High-contrast Navy Blue background with White icons and text. Active states should be indicated by a subtle gold vertical bar on the left edge.
- **Chips/Scores:** Use pill-shaped containers for compatibility scores. High scores (>80%) utilize the Gold accent; low scores (<40%) use the Red accent.