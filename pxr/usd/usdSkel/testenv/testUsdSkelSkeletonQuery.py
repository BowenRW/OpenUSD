#!/pxrpythonsubst
#
# Copyright 2018 Pixar
#
# Licensed under the terms set forth in the LICENSE.txt file available at
# https://openusd.org/license.

from pxr import Usd, UsdGeom, UsdSkel, Gf, Vt
import unittest, random



def _RandomXf():
    return Gf.Matrix4d(Gf.Rotation(Gf.Vec3d(1,0,0),
                                   random.random()*360)*
                       Gf.Rotation(Gf.Vec3d(0,1,0),
                                   random.random()*360)*
                       Gf.Rotation(Gf.Vec3d(0,0,1),
                                   random.random()*360),
                       Gf.Vec3d((random.random()-0.5)*10,
                                (random.random()-0.5)*10,
                                (random.random()-0.5)*10))


def _XformsAreClose(a,b, threshold=1e-5):
    return all(Gf.IsClose(x,y,threshold) for x,y in zip(list(a),list(b)))


class TestUsdSkelSkeletonQuery(unittest.TestCase):


    def assertArrayIsClose(self, a, b, epsilon=1e-4):
        self.assertEqual(len(a), len(b))
        self.assertTrue(all(Gf.IsClose(ca,cb,epsilon)
                            for ca,cb in zip(a,b)))

    
    def test_SkeletonQuery(self):

        random.seed(0)
        numFrames = 10

        stage = Usd.Stage.CreateInMemory()

        skelRoot = UsdSkel.Root.Define(stage, "/SkelRoot")

        anim = UsdSkel.Animation.Define(stage, "/SkelRoot/Anim")
        skel = UsdSkel.Skeleton.Define(stage, "/SkelRoot/Skel")

        binding = UsdSkel.BindingAPI.Apply(skelRoot.GetPrim())
        binding.CreateSkeletonRel().SetTargets(
            [skel.GetPrim().GetPath()])
        binding.CreateAnimationSourceRel().SetTargets(
            [anim.GetPrim().GetPath()])

        skelOrder = Vt.TokenArray(["/A", "/A/B", "/A/B/C",
                                   "/D", "/D/E/F"])
        A,AB,ABC,D,DEF = list(range(len(skelOrder)))

        # Configure the skel.
        skel.GetJointsAttr().Set(skelOrder)
        restXforms = [_RandomXf() for _ in skelOrder]

        topology = UsdSkel.Topology(skelOrder)

        bindWorldXforms = UsdSkel.ConcatJointTransforms(
            topology, Vt.Matrix4dArray(restXforms))

        skel.GetBindTransformsAttr().Set(bindWorldXforms)
        skel.GetRestTransformsAttr().Set(restXforms)

        # Configure root xforms.
        rootXforms = [_RandomXf() for _ in range(numFrames)]
        rootXfAttr = skelRoot.MakeMatrixXform()
        for frame,xf in enumerate(rootXforms):
            rootXfAttr.Set(xf, frame)

        # Configure anim.
        # Leave last element off of anim (tests remapping)
        animOrder = skelOrder[:-1]
        anim.GetJointsAttr().Set(animOrder)

        # Apply joint animations.
        animXforms = {i:[_RandomXf() for _ in range(len(animOrder))]
                      for i in range(numFrames)}
        for frame,xforms in animXforms.items():
            anim.SetTransforms(Vt.Matrix4dArray(xforms), frame)

        #
        # Constuct query and start testing
        # 

        skelCache = UsdSkel.Cache()

        query = skelCache.GetSkelQuery(skel)
        self.assertTrue(query)

        self.assertEqual(hash(query), hash(query))
        self.assertEqual(hash(query), hash(skelCache.GetSkelQuery(skel)))

        # Validate joint rest xform computations.

        xforms = query.ComputeJointLocalTransforms(0, atRest=True)
        expectedXforms = restXforms
        self.assertArrayIsClose(xforms, expectedXforms)

        xfCache = UsdGeom.XformCache()

        # Validate joint xforms computations.
        for t in range(numFrames):

            xforms = animXforms[t]

            xfCache.SetTime(t)

            # Joint local xforms.
            expectedLocalXforms = list(xforms)+[restXforms[-1]]
            computedLocalXforms = query.ComputeJointLocalTransforms(t)
            self.assertArrayIsClose(computedLocalXforms, expectedLocalXforms)

            # Joint skel-space xforms.
            expectedSkelXforms = Vt.Matrix4dArray(
                [
                    xforms[A],
                    xforms[AB]*xforms[A],
                    xforms[ABC]*xforms[AB]*xforms[A],
                    xforms[D],
                    restXforms[DEF]*xforms[D]
                ])
            computedSkelXforms = query.ComputeJointSkelTransforms(t)
            self.assertArrayIsClose(computedSkelXforms, expectedSkelXforms)

            # Joint world space xforms.
            expectedWorldXforms = Vt.Matrix4dArray(
                [expectedSkelXform*rootXforms[t]
                 for i,expectedSkelXform in enumerate(expectedSkelXforms)])
            computedWorldXforms = query.ComputeJointWorldTransforms(xfCache)
            self.assertArrayIsClose(computedWorldXforms, expectedWorldXforms)

            # Joint rest-relative xforms.
            expectedRestRelXforms = Vt.Matrix4dArray(
                [localXf*restXf.GetInverse()
                 for localXf,restXf in zip(expectedLocalXforms, restXforms)])
            computedRestRelXforms = query.ComputeJointRestRelativeTransforms(t)
            self.assertArrayIsClose(computedRestRelXforms,
                                    expectedRestRelXforms)

            #
            # Rest xforms
            #

            # Joint local rest xforms.
            expectedLocalXforms = restXforms
            computedLocalXforms = query.ComputeJointLocalTransforms(t,atRest=True)
            self.assertArrayIsClose(computedLocalXforms, expectedLocalXforms)

            # Joint skel-space rest xforms.
            expectedSkelXforms = Vt.Matrix4dArray(
                [
                    restXforms[A],
                    restXforms[AB]*restXforms[A],
                    restXforms[ABC]*restXforms[AB]*restXforms[A],
                    restXforms[D],
                    restXforms[DEF]*restXforms[D]
                ])
            computedSkelXforms = query.ComputeJointSkelTransforms(0, atRest=True)
            self.assertArrayIsClose(computedSkelXforms, expectedSkelXforms)

            # Joint world space rest xforms.
            expectedWorldXforms = Vt.Matrix4dArray(
                [expectedSkelXform*rootXforms[t]
                 for i,expectedSkelXform in enumerate(expectedSkelXforms)])
            computedWorldXforms = query.ComputeJointWorldTransforms(xfCache, atRest=True)
            self.assertArrayIsClose(computedWorldXforms, expectedWorldXforms)


        # Validate skel instance transforms.
        for frame,expectedXf in enumerate(rootXforms):
            rootXf = skelRoot.GetLocalTransformation(frame)
            self.assertTrue(Gf.IsClose(rootXf, expectedXf, 1e-5))

        #
        # Test that inactivate animation sources have no effect.
        #
        
        anim.GetPrim().SetActive(False)

        skelCache.Clear()

        query = skelCache.GetSkelQuery(skel)

        expectedXforms = restXforms
        computedXforms = query.ComputeJointLocalTransforms(10)
        self.assertArrayIsClose(computedXforms, expectedXforms)

        anim.GetPrim().SetActive(True)

        #
        # Test that blocking transform components of the animation source
        # causes the animation source to be ignored.
        #
        
        anim.GetTranslationsAttr().Block()

        skelCache.Clear()

        query = skelCache.GetSkelQuery(skel)

        expectedXforms = restXforms
        computedXforms = query.ComputeJointLocalTransforms(5)
        self.assertArrayIsClose(computedXforms, expectedXforms)


if __name__ == "__main__":
    unittest.main()
