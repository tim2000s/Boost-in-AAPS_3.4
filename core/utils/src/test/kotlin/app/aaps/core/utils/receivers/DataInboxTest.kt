package app.aaps.core.utils.receivers

import android.content.Context
import androidx.work.ListenableWorker
import com.google.common.truth.Truth.assertThat
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.kotlin.mock

/**
 * The inbox ported 2026-10-06 from upstream (ead83a225d, d6e06f0087), plus the stale re-arm of the
 * pending gate. WorkManager is replaced by a counter so the gate can be observed directly.
 */
class DataInboxTest {

    private object Slot : Inbox<String>("test-slot", ListenableWorker::class.java)
    private object Other : Inbox<String>("other-slot", ListenableWorker::class.java)

    private var now = 1_000_000L
    private val enqueued = mutableListOf<String>()
    private lateinit var inbox: DataInbox

    @BeforeEach fun setUp() {
        inbox = DataInbox(mock<Context>())
        inbox.clock = { now }
        inbox.enqueue = { enqueued += it.workName }
    }

    @Test fun `a burst enqueues one worker and the run drains all of it in order`() {
        repeat(5) { inbox.putAndEnqueue(Slot, "bg$it") }
        assertThat(enqueued).containsExactly("test-slot")
        assertThat(inbox.drain(Slot)).containsExactly("bg0", "bg1", "bg2", "bg3", "bg4").inOrder()
        assertThat(inbox.drain(Slot)).isEmpty()
    }

    @Test fun `after a drain the next value enqueues a fresh worker`() {
        inbox.putAndEnqueue(Slot, "a")
        inbox.drain(Slot)
        inbox.putAndEnqueue(Slot, "b")
        assertThat(enqueued).hasSize(2)
    }

    @Test fun `slots are independent`() {
        inbox.putAndEnqueue(Slot, "a")
        inbox.putAndEnqueue(Other, "x")
        assertThat(enqueued).containsExactly("test-slot", "other-slot")
        assertThat(inbox.drain(Other)).containsExactly("x")
        assertThat(inbox.drain(Slot)).containsExactly("a")
    }

    @Test fun `requeued values go back in front of anything that arrived since`() {
        inbox.putAndEnqueue(Slot, "a")
        val taken = inbox.drain(Slot)
        inbox.putAndEnqueue(Slot, "c")
        inbox.requeue(Slot, taken)
        assertThat(inbox.drain(Slot)).containsExactly("a", "c").inOrder()
    }

    @Test fun `a pending worker that never drains does not block the slot past the stale limit`() {
        // A worker appended behind a failed one is failed by WorkManager without running, so its
        // drain never happens. Upstream's boolean gate then refused every later enqueue.
        inbox.putAndEnqueue(Slot, "a")
        now += DataInbox.STALE_PENDING_MS - 1
        inbox.putAndEnqueue(Slot, "b")
        assertThat(enqueued).hasSize(1)
        now += 1
        inbox.putAndEnqueue(Slot, "c")
        assertThat(enqueued).hasSize(2)
        assertThat(inbox.drain(Slot)).containsExactly("a", "b", "c").inOrder()
    }
}
