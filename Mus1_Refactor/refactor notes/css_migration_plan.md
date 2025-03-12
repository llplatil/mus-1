# CSS Migration Plan for MUS1

## Current Status

- Created unified CSS file (mus1.css) with CSS variables for both themes
- Implement CSS variables for all theme-specific values
- Updated theme switching to use class-based approach
- Added descriptive section comments to organize CSS
- Sperate and organize by type 
- Updated ProjectManager.apply_theme() to use the unified CSS file
- Implemented proper theme propagation through UI hierarchy
- Migrated theme handling to MainWindow as central controller
- Make sure text highlighting issues in input elements dont persist in new css
- Derive QPalette colors from CSS variables

## Implementation Details

### CSS Variable Structure

The unified CSS approach uses a hierarchical variable system:

```css
/* Root variables for light theme (default) */
:root {
  --background-color: #f0f0f0;
  --text-color: #000000;
  /* ...other light theme variables... */
}

/* Dark theme variables */
.dark-theme:root {
  --background-color: #121212;
  --text-color: #ffffff;
  /* ...other dark theme variables... */
}
```

### Variable Mapping

| Variable Name | Dark Theme | Light Theme | Description |
|---------------|------------|-------------|-------------|
| `--background-color` | #121212 | #f0f0f0 | Main background color |
| `--text-color` | #ffffff | #000000 | Main text color |
| `--border-color` | #555555 | #CCCCCC | Border color for elements |
| `--input-background` | #2a2a2a | #FFFFFF | Background for input elements |
| `--selection-background` | #3a5f8c | #ADD8E6 | Background for selected text |

### CSS Components

The CSS is organized into logical sections:

1. **Root Variables**: Base theme definitions
2. **Basic Elements**: Styling for QWidget, etc.
3. **Buttons**: Primary and secondary button styles
4. **Input Elements**: Text inputs, combo boxes, etc.
5. **List and Table Elements**: Styling for list widgets and tables
6. **Navigation Elements**: Nav pane, buttons, etc.
7. **Scrollbars and Containers**: Styling for scrollable elements
8. **Content Areas**: Main content styling

### Theme Handling Architecture

- **CSS Classes**: Theme switching uses .dark-theme class instead of separate files
- **MainWindow**: Central point for theme changes
- **ProjectManager**: Applies theme to application
- **BaseView**: Propagates theme to components

### Theme Application in ProjectManager

```python
def apply_theme(self, app):
    """Apply the chosen theme to the application."""
    # Set QPalette colors
    palette = QPalette()
    theme_mode = self.get_effective_theme()
    if theme_mode == "dark":
        palette.setColor(QPalette.Window, QColor("#121212"))
        # ... other color settings ...
    else:
        palette = app.style().standardPalette()
    app.setPalette(palette)
    
    # Load the unified CSS file
    css_path = Path(__file__).parent.parent / "themes/mus1.css"
    
    # Fallback to unified_css_approach.css if needed
    if not css_path.exists():
        css_path = Path(__file__).parent.parent / "themes/unified_css_approach.css"
        
    with open(css_path, "r") as f:
        app.setStyleSheet(f.read())
```

## Pre-Deletion Checklist

Before deleting the old CSS files, confirm that:

1. ✅ The unified CSS file (`mus1.css`) contains all styling from both themes
2. ✅ The `ProjectManager.apply_theme()` method has been updated to use the unified approach
3. ✅ The `BaseView` class has been updated to properly handle theme classes
4. ✅ The `ProjectView.handle_change_theme()` method has been updated to set theme classes
5. ✅ All components that need theme-specific styling have been assigned the proper CSS classes

## Deletion Steps - done they are in 'Outdated' folder in mus1 refactor -will need to exclude from merge with main

1. Make a backup of the old CSS files (in case something unexpected happens):
   ```
   mkdir -p Mus1_Refactor/themes/backup
   cp Mus1_Refactor/themes/dark.css Mus1_Refactor/themes/backup/
   cp Mus1_Refactor/themes/light.css Mus1_Refactor/themes/backup/
   ```

2. Delete the old CSS files:
   ```
   rm Mus1_Refactor/themes/dark.css
   rm Mus1_Refactor/themes/light.css
   ```

3. Rename the unified CSS file if needed:
   ```
   # Only if the file is still named unified_css_approach.css
   mv Mus1_Refactor/themes/unified_css_approach.css Mus1_Refactor/themes/mus1.css
   ```

4. Test the application thoroughly:
   - Start the application
   - Switch between light and dark themes
   - Verify all components display correctly in both themes
   - Check that theme changes propagate to all views and components

## Text Highlighting Fix

Current issue: Text highlighting in input fields doesn't follow theme colors, and some labels incorrectly use highlighting for backgrounds.

Fix implementation:

```css
/* Fix text selection highlighting */
QLineEdit::selection, QTextEdit::selection, QPlainTextEdit::selection {
  background-color: var(--selection-background);
  color: var(--selection-text-color);
}

/* Input label styling - fixed to remove unwanted highlighting */
.mus1-input-label {
  color: var(--text-color);
  font-weight: normal;
  background-color: transparent; /* No background highlight */
  padding: 2px 0;
}
```

## QPalette Improvements

Currently, QPalette colors are hardcoded in the ProjectManager.apply_theme() method:

```python
palette.setColor(QPalette.Window, QColor("#121212"))
palette.setColor(QPalette.WindowText, QColor("white"))
# ... etc
```

This creates duplicate color definitions (in both QPalette and CSS). The future improvement is to derive QPalette colors from CSS variables:

```python
# Example of future implementation using shared colors
def apply_theme(self, app):
    # Get the same colors used in CSS
    colors = self.get_theme_colors()
    
    # Apply to QPalette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors["--background-color"]))
    palette.setColor(QPalette.WindowText, QColor(colors["--text-color"]))
    # ...etc
    
    app.setPalette(palette)
```

This would maintain a single source of truth for all colors.

## Benefits of the Unified CSS Approach

1. **Single Source of Truth**: Color and style values defined once
2. **Better Organization**: CSS grouped by component type
3. **Easier Theme Switching**: No need to load different files
4. **Simplified Maintenance**: Add new components by updating one file
5. **Consistent Styling**: Border and color variables ensure consistency

## Current Issues

1. **Duplicate Styles**: Same CSS properties are defined twice in both `dark.css` and `light.css` files
2. **Inconsistent Text Highlighting**: Text highlighting in input fields doesn't follow theme colors
3. **No Clear Organization**: Styles are not grouped by component type or functionality
4. **Hard-coded Values**: Color values are hardcoded, making changes require updates in multiple places
5. **Difficult Maintenance**: Adding a new component requires updating multiple CSS files

## Migration Strategy

### Step 1: Create Unified CSS with Variables (Technical Steps)

1. Create a new file `mus1.css` in the `themes/` directory
2. Define CSS variables for all theme-specific values (colors, spacing, etc.)
3. Implement both dark and light theme variables using `:root` and `.dark-theme:root`
4. Organize CSS rules by component type with clear section comments

```css
/* Root variables for light theme (default) */
:root {
  --background-color: #f0f0f0;
  --text-color: #000000;
  /* ...other light theme variables... */
}

/* Dark theme variables */
.dark-theme:root {
  --background-color: #121212;
  --text-color: #ffffff;
  /* ...other dark theme variables... */
}
```

### Step 2: Update Theme Application in ProjectManager

Modify `apply_theme()` method to switch CSS class instead of loading different files:

```python
def apply_theme(self, app):
    """Apply the chosen theme to the application."""
    theme_mode = self.get_effective_theme()
    
    # Load the unified CSS file
    css_file = os.path.join(os.path.dirname(__file__), '..', 'themes', 'mus1.css')
    if os.path.exists(css_file):
        with open(css_file, 'r') as f:
            css_content = f.read()
            app.setStyleSheet(css_content)
    
    # Apply theme class to root widget
    if theme_mode == 'dark':
        app.setProperty('class', 'dark-theme')
    else:
        app.setProperty('class', '')  # Light theme is default
    
    # Force style refresh
    app.style().unpolish(app)
    app.style().polish(app)
```

### Step 3: Fix Text Highlighting Issues

1. Identify problematic selectors in current CSS:
   - Text selection handling in input fields
   - Label backgrounds that use highlighting unnecessarily

2. Replace with proper variable-based styling:

```css
/* Fix text selection highlighting */
QLineEdit::selection, QTextEdit::selection, QPlainTextEdit::selection {
  background-color: var(--selection-background);
  color: var(--selection-text-color);
}

/* Input label styling - fixed to remove unwanted highlighting */
.mus1-input-label {
  color: var(--text-color);
  font-weight: normal;
  background-color: transparent; /* No background highlight */
  padding: 2px 0;
}
```

### Step 4: Implement Incremental Migration

To avoid breaking existing functionality, implement migration in phases:

#### Phase 1: Add Organizational Comments to Existing CSS Files

Add section comments to current CSS files to start organizing them:

```css
/* === BUTTON STYLES === */
.mus1-primary-button { /* ... */ }
.mus1-secondary-button { /* ... */ }

/* === INPUT ELEMENTS === */
.mus1-text-input { /* ... */ }
.mus1-combo-box { /* ... */ }
```

#### Phase 2: Create Mapping Document

Create a mapping document that tracks each CSS property and its corresponding variable:

| Property | Light Theme Value | Dark Theme Value | Variable Name |
|----------|-------------------|------------------|--------------|
| Background | #f0f0f0 | #121212 | --background-color |
| Text Color | #000000 | #ffffff | --text-color |
| ... | ... | ... | ... |

#### Phase 3: Test Theme Switching with Both Approaches

Implement temporary code in `apply_theme()` that allows testing the new approach:

```python
def apply_theme(self, app):
    """Apply the chosen theme to the application."""
    theme_mode = self.get_effective_theme()
    
    # Determine whether to use unified CSS (test flag)
    use_unified_css = os.environ.get('MUS1_UNIFIED_CSS', '0') == '1'
    
    if use_unified_css:
        # New approach with unified CSS
        css_file = os.path.join(os.path.dirname(__file__), '..', 'themes', 'mus1.css')
        if os.path.exists(css_file):
            with open(css_file, 'r') as f:
                css_content = f.read()
                app.setStyleSheet(css_content)
                
        # Apply theme class
        app.setProperty('class', 'dark-theme' if theme_mode == 'dark' else '')
    else:
        # Current approach with separate files
        css_file = os.path.join(os.path.dirname(__file__), '..', 'themes', f'{theme_mode}.css')
        if os.path.exists(css_file):
            with open(css_file, 'r') as f:
                css_content = f.read()
                app.setStyleSheet(css_content)
    
    # Force style refresh
    app.style().unpolish(app)
    app.style().polish(app)
```

#### Phase 4: Complete Migration

After testing confirms the unified approach works:

1. Remove the separate theme files
2. Update documentation
3. Remove the temporary flag-based code

## Border and Color Maintenance Improvements

### Create a Border Style System

Define border styles as variables to ensure consistency:

```css
:root {
  /* Border style variables */
  --border-thin: 1px solid var(--border-color);
  --border-medium: 2px solid var(--border-color);
  --border-accent: 1px solid var(--accent-color);
  --border-error: 1px solid var(--error-color);
  
  /* Border radius variables */
  --radius-small: 3px;
  --radius-medium: 6px;
  --radius-large: 10px;
}
```

Apply these consistently:

```css
.mus1-input-group {
  border: var(--border-thin);
  border-radius: var(--radius-medium);
  /* other properties */
}
```

### Color Variable Hierarchy

Implement a hierarchical color system:

```css
:root {
  /* Base colors */
  --primary-color: #4A90E2;
  --secondary-color: #6FCF97;
  --neutral-color: #888888;
  --error-color: #EB5757;
  --warning-color: #F2C94C;
  --success-color: #6FCF97;
  
  /* Derived colors (light theme) */
  --primary-light: #6BA8E5;
  --primary-dark: #357ABD;
  
  /* Functional colors */
  --button-primary-bg: var(--primary-color);
  --button-primary-hover: var(--primary-dark);
  --input-border-color: var(--neutral-color);
  --input-focus-border: var(--primary-color);
}
```

## Benefits of This Approach

1. **Single Source of Truth**: Color and style values defined once
2. **Better Organization**: CSS grouped by component type
3. **Easier Theme Switching**: No need to load different files
4. **Simplified Maintenance**: Add new components by updating one file
5. **Consistent Styling**: Border and color variables ensure consistency

## Required CSS Changes for Text Highlighting Fix

Current issue: Text highlighting in input fields doesn't follow theme colors, and some labels incorrectly use highlighting for backgrounds.

### Changes in Light Theme:

```css
/* Before */
QLineEdit::selection, QTextEdit::selection {
  background-color: #ADD8E6;  /* Hardcoded light blue */
}

/* After */
QLineEdit::selection, QTextEdit::selection, QPlainTextEdit::selection {
  background-color: var(--selection-background);  /* Variable */
  color: var(--selection-text-color);
}
```

### Changes in Dark Theme:

```css
/* Before */
QLineEdit::selection, QTextEdit::selection {
  background-color: #3a5f8c;  /* Hardcoded dark blue */
}

/* After */
QLineEdit::selection, QTextEdit::selection, QPlainTextEdit::selection {
  background-color: var(--selection-background);  /* Variable */
  color: var(--selection-text-color);
}
```

### Fix for Input Labels:

```css
/* Before - Labels in both themes incorrectly used background highlight */
.mus1-input-label {
  background-color: #e0e0e0;  /* Incorrect highlighting */
}

/* After */
.mus1-input-label {
  color: var(--text-color);
  font-weight: normal;
  background-color: transparent;  /* No background highlight */
  padding: 2px 0;
}
``` 