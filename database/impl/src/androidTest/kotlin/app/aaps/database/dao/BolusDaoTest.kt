package app.aaps.database.dao

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.aaps.database.AppDatabase
import app.aaps.database.entities.Bolus
import app.aaps.database.entities.embedments.InterfaceIDs
import org.junit.After
import org.junit.Assert
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Glucagon shares the bolus table; the insulin queries must never return it. */
@RunWith(AndroidJUnit4::class)
class BolusDaoTest {

    private lateinit var db: AppDatabase
    private val t0 = 1_700_000_000_000L

    @Before
    fun setUp() {
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Context>(), AppDatabase::class.java).build()
        // pumpId set on every row so the sync query's pumpId filter cannot be what excludes glucagon
        fun bolus(minutes: Long, amount: Double, type: Bolus.Type, valid: Boolean = true) =
            Bolus(timestamp = t0 + minutes * 60_000L, amount = amount, type = type, isValid = valid, interfaceIDs_backing = InterfaceIDs(pumpId = minutes + 1))
        db.bolusDao.insert(bolus(0, 2.0, Bolus.Type.NORMAL))
        db.bolusDao.insert(bolus(5, 0.1, Bolus.Type.GLUCAGON))
        db.bolusDao.insert(bolus(10, 0.3, Bolus.Type.SMB))
        db.bolusDao.insert(bolus(15, 0.05, Bolus.Type.GLUCAGON, valid = false))
    }

    @After
    fun tearDown() = db.close()

    private fun List<Bolus>.types() = map { it.type }.toSet()

    @Test
    fun insulinQueriesExcludeGlucagon() {
        Assert.assertEquals(setOf(Bolus.Type.NORMAL, Bolus.Type.SMB), db.bolusDao.getBolusesFromTime(t0).blockingGet().types())
        Assert.assertEquals(setOf(Bolus.Type.NORMAL, Bolus.Type.SMB), db.bolusDao.getBolusesFromTime(t0, t0 + 3_600_000L).blockingGet().types())
        Assert.assertEquals(setOf(Bolus.Type.NORMAL, Bolus.Type.SMB), db.bolusDao.getBolusesIncludingInvalidFromTime(t0).blockingGet().types())
        Assert.assertEquals(Bolus.Type.SMB, db.bolusDao.getLastBolusRecord().blockingGet()!!.type)
    }

    @Test
    fun syncQuerySkipsGlucagon() {
        val synced = generateSequence(db.bolusDao.getNextModifiedOrNewAfterExclude(0).blockingGet()) {
            db.bolusDao.getNextModifiedOrNewAfterExclude(it.id).blockingGet()
        }.toList()
        Assert.assertEquals(listOf(Bolus.Type.NORMAL, Bolus.Type.SMB), synced.map { it.type })
    }

    @Test
    fun glucagonQueriesReturnOnlyGlucagon() {
        Assert.assertEquals(listOf(0.1), db.bolusDao.getGlucagonFromTime(t0).blockingGet().map { it.amount })
        Assert.assertEquals(listOf(0.1, 0.05), db.bolusDao.getGlucagonIncludingInvalidFromTime(t0).blockingGet().map { it.amount })
        Assert.assertEquals(emptyList<Bolus>(), db.bolusDao.getGlucagonFromTime(t0 + 6 * 60_000L).blockingGet())
    }
}
