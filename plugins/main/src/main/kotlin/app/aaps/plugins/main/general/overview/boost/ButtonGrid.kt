package app.aaps.plugins.main.general.overview.boost

import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout

/**
 * Lays the overview action buttons out in rows of at most [MAX_PER_ROW], computed from the buttons
 * that are visible at the time of the call. Each row shares its width equally between its buttons,
 * and every button in a row is stretched to the height of the tallest, so a two-line quick-wizard
 * label does not leave its neighbours short.
 *
 * Buttons are shown and hidden by preferences and pump/profile state, so the row structure cannot be
 * fixed in XML: [arrange] is called after each visibility pass and rebuilds the rows only when the
 * visible set has changed. The button views themselves are moved between rows rather than recreated,
 * so their ids, click and long-click listeners, colours and accessibility labels are untouched.
 */
object ButtonGrid {

    const val MAX_PER_ROW = 3

    /** Row sizes for [count] visible buttons: 4 gives [3, 1], 8 gives [3, 3, 2]. */
    fun rowSizes(count: Int, maxPerRow: Int = MAX_PER_ROW): List<Int> {
        require(maxPerRow > 0) { "maxPerRow must be positive" }
        if (count <= 0) return emptyList()
        return List((count + maxPerRow - 1) / maxPerRow) { row -> minOf(maxPerRow, count - row * maxPerRow) }
    }

    /**
     * Rebuilds [container] as a vertical stack of horizontal rows holding [buttons] in their given
     * order. Hidden buttons are kept attached at the end of the last row, where a GONE child takes no
     * space; were one made visible without a further call it would still appear rather than be lost.
     */
    fun arrange(container: LinearLayout, buttons: List<View>, gapPx: Int, rowGapPx: Int, maxPerRow: Int = MAX_PER_ROW) {
        val visible = buttons.filter { it.visibility != View.GONE }
        val hidden = buttons.filter { it.visibility == View.GONE }
        val signature = buttons.map { System.identityHashCode(it) to (it.visibility != View.GONE) }
        val alreadyArranged = container.tag == signature &&
            buttons.all { (it.parent as? View)?.parent === container }
        if (alreadyArranged) return

        for (b in buttons) (b.parent as? ViewGroup)?.removeView(b)
        container.removeAllViews()
        container.orientation = LinearLayout.VERTICAL

        val rows = mutableListOf<LinearLayout>()
        var index = 0
        for ((rowIndex, size) in rowSizes(visible.size, maxPerRow).withIndex()) {
            val row = newRow(container, if (rowIndex > 0) rowGapPx else 0)
            for (i in 0 until size) addToRow(row, visible[index++], if (i > 0) gapPx else 0)
            rows += row
        }
        if (hidden.isNotEmpty()) {
            val last = rows.lastOrNull() ?: newRow(container, 0).also { rows += it }
            for (b in hidden) addToRow(last, b, if (last.childCount > 0) gapPx else 0)
        }
        container.tag = signature
    }

    private fun newRow(container: LinearLayout, topMarginPx: Int): LinearLayout =
        LinearLayout(container.context).also { row ->
            row.orientation = LinearLayout.HORIZONTAL
            row.isBaselineAligned = false
            container.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).also { it.topMargin = topMarginPx })
        }

    private fun addToRow(row: LinearLayout, button: View, startMarginPx: Int) {
        row.addView(button, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).also { it.marginStart = startMarginPx })
    }
}
