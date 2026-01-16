# Geovivienda Style Guide

This document defines the visual design language for the Geovivienda application, ensuring consitency across all interfaces. The design is inspired by the "UrbanNest" aesthetic, focusing on clean lines, high readability, and a modern feel.

## 1. Color Palette

### Primary Colors
Used for primary actions, active states, and key brand elements.
- **Royal Blue**: `#3B82F6` (Main Action Color - e.g., "Apply Now" buttons)
- **Dark Blue**: `#1E40AF` (Hover states)

### Neutral Colors
Used for backgrounds, borders, and general layout structure.
- **White**: `#FFFFFF` (Card backgrounds, Main content areas)
- **Light Gray**: `#F3F4F6` (App background, Section dividers)
- **Border Gray**: `#E5E7EB` (Input borders, Card outlines)

### Text Colors
- **Headings (Dark Slate)**: `#1F2937` (High contrast for readability)
- **Body Text (Gray)**: `#6B7280` (Softer for long-form content)
- **Links/Accents**: `#2563EB`

### Semantic Colors
Used to convey status or categories.
- **Success (Green)**: `#10B981` (e.g., "Excellent" scores, Positive indicators)
- **Info (Light Blue)**: `#EFF6FF` (Backgrounds for tags/badges)
- **Warning/Error**: `#EF4444`

---

## 2. Typography

**Font Family**: `Inter`, `Roboto`, or system sans-serif.

| Usage | Weight | Size (approx) | Color |
| :--- | :--- | :--- | :--- |
| **Page Title (H1)** | Bold (700) | 2rem (32px) | Dark Slate |
| **Section Heading (H2)**| Semi-Bold (600)| 1.5rem (24px) | Dark Slate |
| **Card Title (H3)** | Semi-Bold (600)| 1.25rem (20px)| Dark Slate |
| **Body Text** | Regular (400) | 1rem (16px) | Gray |
| **Labels/Metas** | Medium (500) | 0.875rem (14px)| Gray |

---

## 3. UI Components

### Buttons
- **Primary Button**:
  - Background: Royal Blue (`#3B82F6`)
  - Text: White
  - Border Radius: `8px`
  - Padding: `12px 24px`
  - Font Weight: Semi-Bold
- **Secondary Button**:
  - Background: White
  - Border: 1px solid Border Gray (`#E5E7EB`)
  - Text: Dark Slate
  - Border Radius: `8px`

### Cards
- **Background**: White
- **Border Radius**: `12px` or `16px`
- **Shadow**: Soft, diffused shadow (e.g., `box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1)`)
- **Spacing**: Generous internal padding (`24px`)

### Badges / Tags
- **Shape**: Pill-shaped (Fully rounded corners)
- **Style**: Light background with darker text color
  - *Example (Top Rated)*: Background `#ECFDF5` (Light Green), Text `#059669` (Dark Green)
  - *Example (Tag)*: Background `#EFF6FF` (Light Blue), Text `#1D4ED8` (Dark Blue)

---

## 4. Layout & Spacing

- **Container**: Centered, max-width approx `1200px` or `1440px`.
- **Grid System**: Flexible grid (CSS Grid/Flexbox) for listing items.
- **Whitespace**: extensive use of whitespace to separate sections, avoiding clutter.
