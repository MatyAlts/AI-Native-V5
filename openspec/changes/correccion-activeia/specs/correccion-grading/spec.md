## MODIFIED Requirements

### Requirement: Grading view in web-teacher
The web-teacher SHALL include a "Correcciones" section accessible from the sidebar. It SHALL display a list of entregas filtered by comision and estado, with drill-down to a grading form showing the rubrica criteria, score inputs per criterion, and a general feedback textarea.

The grading form SHALL additionally offer, for entregas with a persisted artefacto, an action to download the submitted source, and per-exercise actions to request an Active-IA correction and to view its result. The result SHALL be presented as a suggestion: the grade is only persisted when the teacher explicitly grades.

#### Scenario: Teacher navigates to grading view
- **WHEN** a teacher clicks "Correcciones" in the sidebar
- **THEN** a list of entregas for the selected comision is displayed with columns: student pseudonym, TP title, estado, submitted_at

#### Scenario: Teacher opens grading form
- **WHEN** a teacher clicks on a submitted entrega
- **THEN** a grading form appears with: rubrica criteria from the TP, score input per criterion, feedback textarea, and "Calificar" button

#### Scenario: Teacher downloads the submitted source
- **WHEN** the entrega has a persisted artefacto
- **THEN** the grading form SHALL offer an action to download it

#### Scenario: Teacher requests a correction for one exercise
- **WHEN** the teacher activates the correction action on an exercise card
- **THEN** the correction SHALL be requested for that exercise only, and its progress SHALL be shown until it completes or fails

#### Scenario: Correction result never grades by itself
- **WHEN** a correction completes with a grade
- **THEN** the grade SHALL be displayed as a suggestion
- **AND** the entrega SHALL remain ungraded until the teacher submits the grading form
