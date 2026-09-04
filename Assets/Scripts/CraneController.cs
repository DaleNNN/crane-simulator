using UnityEngine;

public class CraneController : MonoBehaviour
{
    public Transform slew;
    public Transform boomPivot;
    public Transform telescope;

    public float slewAngle;
    public float boomAngle;
    public float telescopeExtension;

    private Vector3 telescopeStartPosition;

    void Start()
    {
        telescopeStartPosition = telescope.localPosition;
    }

    void Update()
    {
        slew.localRotation =
            Quaternion.Euler(0f, slewAngle, 0f);

        boomPivot.localRotation =
            Quaternion.Euler(boomAngle, 0f, 0f);

        telescope.localPosition =
            telescopeStartPosition +
            new Vector3(0f, 0f, telescopeExtension);
    }
}